# Adversarial Audit Report — Current MVP State

**Audit date:** 2026-09-17

**Reviewer role:** Principal Architect / Lead Security & QA Reviewer

**Final verdict:** **[BLOCKED - CẦN SỬA TRƯỚC]**

## 1. Phạm vi và nguyên tắc kiểm tra

Báo cáo này kiểm tra trực tiếp implementation hiện tại dựa trên các nguồn sự thật sau:

- `thesis/tro_ly_phoi_do_thong_minh_multi_agent.md`
- `docs/01_product/PRD_MVP.md`
- `docs/04_data/DATA_SCHEMA.md`
- `docs/05_api/API_CONTRACT.md`
- Các feature, architecture và test specification liên quan

Trạng thái test xanh không được xem là bằng chứng rằng implementation đã đúng. Audit tập trung vào contract thực tế, business invariants, concurrency, failure modes, false-positive tests và frontend state drift.

## 2. Executive conclusion

Trạng thái hiện tại chưa đủ an toàn để tuyên bố hoàn thành MVP. Có các lỗi race condition, idempotency giả, vi phạm vòng đời dữ liệu ảnh, sai lệch giữa recommendation và try-on, cùng nhiều bài test xanh nhưng không kiểm tra hành vi tích hợp thật.

## 3. [CRITICAL]

### 3.1. Hủy ingestion có thể bị background worker hồi sinh

**Mã liên quan:**

- `backend/app/services/ingestion_service.py:169-175`
- `backend/app/services/ingestion_service.py:194-351`
- `backend/app/services/cleanup_service.py:29-95`
- `backend/app/api/v1/endpoints/ingestion.py:155-165`

Worker chỉ kiểm tra `PROCESSING` một lần ở đầu. Sau đó nó chạy detector/provider, tạo crop, rồi vô điều kiện ghi `NEEDS_REVIEW`.

Kịch bản lỗi:

1. Upload trả `202`, background task bắt đầu.
2. Người dùng bấm hủy.
3. `cancel_ingestion_batch()` xóa object và đánh dấu `EXPIRED`.
4. Worker cũ tiếp tục tạo crop và ghi lại `NEEDS_REVIEW`.
5. Batch đã hủy bị hồi sinh, tài sản riêng tư mới tiếp tục tồn tại.

Race tương tự giữa cancel và confirm còn có thể tạo `WardrobeItem` trỏ đến media đã bị xóa.

**Cách sửa:**

- Dùng atomic state transition/CAS, ví dụ `UPDATE ... WHERE status='processing' AND version=:old`.
- Kiểm tra trạng thái lại trước mỗi lần ghi object và trước commit cuối.
- Serialize `process/cancel/confirm` bằng row lock hoặc optimistic version.
- Có cancellation token cho job.
- Mọi object được tạo sau khi cancel phải đi vào compensating cleanup.

### 3.2. Confirm ingestion không thực sự idempotent khi double-click

**Mã liên quan:**

- `backend/app/services/ingestion_service.py:418-450`
- `backend/app/services/ingestion_service.py:475-590`
- `backend/app/models/entities.py:271-275`
- `frontend/src/components/ingestion/IngestionWorkflow.tsx:154-169`
- `backend/app/api/v1/endpoints/ingestion.py:193-205`

Hai request đồng thời đều có thể đọc `NEEDS_REVIEW`, cùng tạo `WardrobeItem`, rồi cùng commit. Unique constraint chỉ làm request thua cuộc ném `IntegrityError` và trả 500.

Frontend còn tạo `idempotency_token` mới cho mỗi lần gọi, trong khi backend không sử dụng token này.

**Cách sửa:**

- Lưu idempotency key trong DB với unique constraint theo `user + batch + key`.
- Ràng buộc key với fingerprint của payload.
- Atomic transition `NEEDS_REVIEW -> CONFIRMED`.
- Khi gặp unique race, rollback rồi trả lại kết quả đã commit thay vì 500.
- Frontend dùng mutex/ref để chống double-submit và tái sử dụng cùng token khi retry.

### 3.3. Có thể thất thoát object riêng tư vĩnh viễn sau rollback DB

**Mã liên quan:**

- `backend/app/services/ingestion_service.py:93-151`
- `backend/app/services/ingestion_service.py:355-362`
- `backend/app/services/tryon_service.py:183-230`

Object được upload trước khi DB commit. Nếu DB lỗi và lệnh xóa bù cũng lỗi, hệ thống chỉ ghi log rồi quên object đó. Sau rollback không còn bản ghi nào để cleanup job tìm lại.

Đây là vi phạm trực tiếp yêu cầu Object Storage: cleanup thất bại phải retryable và observable. Với original/try-on image, đây còn là rủi ro lưu giữ dữ liệu riêng tư không thời hạn.

**Cách sửa:**

- Dùng durable cleanup outbox/orphan registry.
- Ghi manifest hoặc staging record trước khi upload.
- Chỉ đánh dấu hoàn tất sau cả object và DB state đã hội tụ.
- Có worker retry, metric, cảnh báo và retention SLA.
- Không được dùng `except Exception: pass` cho cleanup failure.

### 3.4. Recommendation hợp lệ gồm 5 món luôn thất bại khi try-on

**Mã liên quan:**

- `backend/app/agents/fashion_agent.py:88-118`
- `backend/app/agents/fashion_agent.py:113`
- `backend/app/agents/coordinator.py:213-252`
- `backend/app/services/tryon_service.py:62-71`

Fashion Agent chủ động sinh tổ hợp `top + bottom + footwear + outerwear + accessory`, tức 5 món. Coordinator xem cấu hình này là hợp lệ. Try-on lại chỉ chấp nhận từ 2 đến 4 món và ném `TryOnFailedError` trước cả provider/fallback.

Một recommendation đúng theo logic stylist vì vậy không thể đi qua luồng lookbook của chính hệ thống.

**Cách sửa:**

- Hỗ trợ 5 món trong try-on và moodboard; hoặc
- Cấm tổ hợp có đồng thời outerwear và accessory tại Fashion Agent/Coordinator.
- Thêm integration test recommendation 5 món đi qua try-on thành công.

### 3.5. Error envelope không được bảo đảm trên lỗi thực tế

**Mã liên quan:**

- `backend/app/main.py:43-72`
- `backend/app/api/v1/endpoints/media.py:41-45`
- `backend/app/services/tryon_service.py:216-230`
- `frontend/src/lib/api.ts:154-166`

Global handlers chỉ bao phủ `AppException` và lỗi validation. Lỗi DB, storage, `IntegrityError` hay lỗi ngoài dự kiến có thể rơi vào response 500 mặc định, không bảo đảm envelope trong `API_CONTRACT.md`.

Frontend lại giả định response là JSON. Khi server trả plain 500, lỗi gốc bị biến thành `INVALID_RESPONSE`, làm mất khả năng chẩn đoán.

**Cách sửa:**

- Thêm catch-all handler trả error envelope chuẩn cùng correlation ID.
- Map rõ storage failure, conflict và database failure.
- Log stack trace ở server nhưng không trả chi tiết nội bộ cho client.
- Thêm negative integration tests cho MinIO failure, DB conflict và exception không dự kiến.

## 4. [MAJOR]

### 4.1. Có thể confirm batch dù chưa review hết detections

`backend/app/services/ingestion_service.py:472-480` cho phép bỏ qua detection, nhưng `:588-590` vẫn đánh dấu toàn bộ batch `CONFIRMED`. Các detection bị bỏ qua tiếp tục ở `PROPOSED` nhưng không còn đường review.

**Cách sửa:** payload phải bao phủ chính xác toàn bộ detection đang `PROPOSED`, hoặc bổ sung trạng thái `PARTIALLY_REVIEWED`.

### 4.2. Detector lỗi dẫn đến màn hình manual review không thể hoàn tất

`backend/app/services/ingestion_service.py:202-225` chuyển sang `NEEDS_REVIEW` nhưng không tạo detection. Frontend yêu cầu ít nhất một accepted detection mới bật confirm tại `frontend/src/components/ingestion/IngestionWorkflow.tsx:70-86` và `:221`.

Integration test `backend/tests/integration/test_ingestion_flow.py:450-484` chỉ kiểm tra status/warning, không chứng minh user có thể hoàn tất luồng.

**Cách sửa:** tạo full-image provisional detection hoặc cung cấp UI vẽ vùng/manual item creation; test phải đi tới confirm thành công.

### 4.3. Feedback cadence sai khi timeout, retry hoặc gửi song song

`backend/app/api/v1/endpoints/stylist.py:305-311` tăng cadence trước khi client nhận response. Service chỉ deduplicate theo outfit ID tại `backend/app/services/feedback_cadence_service.py:59-94`.

Nếu response bị mất, retry tạo outfit ID mới và tăng count lần nữa dù người dùng chỉ thấy một recommendation. Hai submit song song cũng có thể làm cadence tiến sai.

**Cách sửa:** thêm idempotency key cho stylist request hoặc delivery ACK; lưu và trả lại cùng recommendation khi retry; test timeout-after-commit và concurrent submission.

### 4.4. Chỉnh profile có thể xóa sai dữ liệu personalization đã học

`backend/app/services/profile_service.py:130-146` thay toàn bộ `learned_feature_weights` bằng trọng số onboarding, nhưng giữ nguyên `ratings_count`. `backend/app/agents/personalization_agent.py:209-235` lại coi trường đó là tín hiệu học từ rating khi đủ số đánh giá.

**Cách sửa:** tách `onboarding_preference_weights` và `learned_rating_weights`, hoặc rebuild learned weights từ rating history sau khi cập nhật profile.

### 4.5. Media endpoint lệch contract và làm lộ user ID trong URL

- `backend/app/api/v1/endpoints/media.py:16-26` cho phép `user_id` query thay cho `X-User-Id`.
- `frontend/src/lib/api.ts:264-275` gắn user ID vào media URL.

Query parameter này không có trong API contract và dễ xuất hiện trong browser history, access log, reverse-proxy log hoặc referrer.

Dù production authentication nằm ngoài MVP, đây vẫn là sai lệch identity boundary đã quy định.

**Cách sửa:** bỏ query fallback; dùng authenticated request/header hoặc opaque signed URL có hạn sử dụng, không dùng raw user ID.

### 4.6. Frontend và backend dùng enum/schema khác nhau

- `frontend/src/types/chat.ts:1`: `top | bottom | shoes`.
- `frontend/src/types/outfits.ts:4`: thiếu `dress`, dùng `shoes`.
- `backend/app/models/entities.py:86-107`: dùng `footwear` và có `dress`.
- `frontend/src/__tests__/useStylistChat.test.ts:34-50`: tiếp tục mock `slot: "shoes"`.
- `UploadBatchResponse` frontend yêu cầu `item_count`, trong khi backend không trả trường này.

Do `frontend/src/lib/api.ts:154-169` ép kiểu trực tiếp mà không runtime validation, TypeScript không phát hiện response thực tế sai giả định.

**Cách sửa:** generate TypeScript types từ OpenAPI hoặc schema dùng chung; thêm runtime validation; test fixture phải có `dress`, `footwear`, outerwear và accessory.

### 4.7. Giới hạn input không thống nhất

Frontend cho location dài 200 ký tự tại `frontend/src/hooks/useStylistChat.ts:43-48` và `frontend/src/components/chat/ChatComposer.tsx:111-118`, trong khi backend chỉ nhận 100 tại `backend/app/schemas/stylist.py:11-16`. Ngược lại, query backend không có giới hạn đủ chặt dù client giới hạn 1000.

**Cách sửa:** quy định giới hạn tại API contract, enforce ở backend và generate constraint cho frontend.

### 4.8. Deployment configuration bị hardcode

- `backend/app/core/config.py:21-46` định nghĩa frontend URL và bucket names.
- `backend/app/main.py:34-39` lại hardcode localhost CORS.
- `backend/app/services/ingestion_service.py:97-106` và `:237-257` hardcode tên bucket.

Cấu hình môi trường có thể hợp lệ nhưng ứng dụng vẫn ghi vào bucket khác hoặc browser production bị CORS chặn.

**Cách sửa:** inject settings/storage bucket configuration vào service; CORS phải lấy từ allow-list cấu hình.

### 4.9. Không có cơ chế vận hành bảo đảm cleanup trong 24 giờ

Repo có cleanup script, nhưng không có scheduler/worker/CronJob trong cấu hình triển khai. Yêu cầu xóa transient assets trong 24 giờ mới chỉ tồn tại ở cấp hàm, chưa được bảo đảm trong runtime.

**Cách sửa:** thêm scheduled service/CronJob, metric lần chạy gần nhất, số object thất bại và cảnh báo khi job ngừng.

### 4.10. Frontend có nhiều điểm state drift và swallowed error

- Polling dùng `setInterval` với hàm async tại `frontend/src/components/ingestion/IngestionWorkflow.tsx:109`: request có thể chồng lên nhau, response cũ ghi đè response mới.
- Hủy ingestion nuốt lỗi rồi reset local state tại `IngestionWorkflow.tsx:184-203`.
- Dismiss rating nuốt lỗi nhưng đóng prompt tại `frontend/src/components/feedback/RatingPrompt.tsx:77-91`.
- Unbookmark chỉ đổi cờ, không loại item khỏi danh sách saved hoặc cập nhật total tại `frontend/src/app/saved/page.tsx:79-89`.
- Try-on modal không abort hoặc sequence request cũ tại `frontend/src/components/tryon/TryOnModal.tsx:42-67`.

**Cách sửa:** recursive awaited polling, `AbortController`/sequence ID, hiển thị trạng thái chưa đồng bộ, refetch hoặc cập nhật cache/total đúng nghĩa.

### 4.11. Timeout provider không thực sự dừng tác vụ

`backend/app/services/image_generation.py:84-100` timeout một `Future`, nhưng Python thread đang chạy thường không bị hủy. Nhiều provider call bị treo có thể tích lũy thread dù API đã trả moodboard fallback.

**Cách sửa:** provider-level HTTP timeout, shared bounded executor, circuit breaker và load test với provider liên tục treo.

### 4.12. Database chưa bảo vệ đầy đủ outfit invariants

`OutfitItem` tại `backend/app/models/entities.py:439-459` không enforce branch `top+bottom` XOR `dress`, cardinality hoặc item active. Coordinator kiểm tra trên đường recommendation hiện tại, nhưng DB vẫn chấp nhận dữ liệu sai từ script, test helper hoặc luồng mới.

**Cách sửa:** centralize mọi ghi outfit qua một transaction service; thêm trigger/finalization validation hoặc mô hình branch có constraint rõ ràng.

### 4.13. UUID contract không được enforce

`backend/app/api/dependencies.py:52-61` chỉ kiểm tra header không rỗng; nhiều path chỉ giới hạn độ dài. Các giá trị như `user-404` vẫn có thể được persist dù data schema mô tả ID dạng UUID.

**Cách sửa:** parse bằng kiểu UUID tại boundary, thống nhất version policy và bổ sung DB constraint/migration nếu cần.

### 4.14. Chức năng Wardrobe phía frontend chưa đáp ứng phạm vi PRD

`frontend/src/app/wardrobe/page.tsx:58-61` chỉ hiển thị ingestion workflow. Không có danh sách wardrobe, search/filter, edit hoặc delete dù backend đã có API và PRD yêu cầu quản lý tủ đồ.

**Cách sửa:** bổ sung wardrobe inventory UI và E2E thật cho CRUD, filter và active/inactive state.

### 4.15. Test suite có nhiều false-positive rõ ràng

- `frontend/e2e/golden-scenario.spec.ts:14-112` mock toàn bộ API, nên không kiểm tra header, DTO, persistence, DB hay error envelope. Mock `mark-worn` còn thiếu `wear_log_id` nhưng test vẫn pass.
- `backend/tests/test_openapi_contract.py:14-318` chỉ cherry-pick một số route/property; không phát hiện header được khai báo optional, media query thừa hoặc thiếu response status.
- `backend/tests/unit/test_vision_normalization.py:74-90` kiểm tra output từ fake provider, không kiểm tra normalization của live provider.
- `frontend/src/__tests__/savedOutfitsPage.test.tsx:217-238` chỉ assert API được gọi, không assert item biến mất và total thay đổi.

**Cách sửa:** thêm browser-to-real-backend golden test với DB/storage tạm; exact OpenAPI snapshot/diff; malformed provider fixtures; assert DB/session-storage/network payload và UI side effects.

## 5. [MINOR / SUGGESTION]

- `ApiSuccessResponse<T>` phía frontend không biểu diễn bắt buộc `success: true`; nên dùng discriminated union cho success/error.
- Pydantic request models nên cân nhắc `extra="forbid"` để typo hoặc trường ngoài contract không bị bỏ qua âm thầm.
- `frontend/src/lib/api.ts:78-81` trả UUID toàn số 0 khi SSR; đây không phải session UUIDv4 hợp lệ.
- `_load_outfit_assets()` trong `backend/app/services/tryon_service.py:76-100` thực hiện nhiều query theo từng outfit item; có thể eager-load/join để giảm N+1 sau khi sửa correctness.

## 6. Thứ tự sửa bắt buộc

1. Race `process/cancel/confirm` và idempotency DB.
2. Durable cleanup/outbox cho object storage.
3. Đồng bộ cardinality recommendation và try-on.
4. Chuẩn hóa error envelope.
5. Sửa feedback delivery/idempotency.
6. Đồng bộ OpenAPI, backend và frontend types.
7. Thay mocked golden E2E bằng ít nhất một luồng browser-to-backend thật.

## 7. Final verdict

Cho đến khi các mục **CRITICAL** được sửa và có concurrency/negative tests chứng minh hành vi thực tế, kết luận vẫn là:

**[BLOCKED - CẦN SỬA TRƯỚC]**
