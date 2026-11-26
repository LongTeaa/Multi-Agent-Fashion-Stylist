# Review toàn dự án trước khi viết báo cáo và deploy — 2026-11-26

Thực hiện trên `main` tại `34dbe2e` (đã đồng bộ với `origin/main`, không có nhánh chưa merge). Mục đích: xác nhận trạng thái hiện tại, liệt kê những gì chặn việc deploy công khai, và đối chiếu bằng chứng đã có với bố cục 8 chương của mẫu `thesis/Mau bao cao KLTN_DS.docx`.

## 1. Kiểm tra đã chạy

| Lệnh | Kết quả |
| :--- | :--- |
| `cd backend; python -m pytest -q` | 976 passed, 32 warnings, 9 phút 04 giây |
| `cd frontend; npx vitest run` (từ `D:\`) | 18 files, 132 passed |
| `npx tsc --noEmit` | sạch |
| `npx next build` | thành công, 8 route tĩnh |
| `npx eslint .` | **1 lỗi**: `react-hooks/set-state-in-effect` tại `frontend/src/components/tryon/TryOnModal.tsx:227` (lỗi đã biết, trước ghi là dòng 223) |
| `./scripts/verify_documentation.ps1` | passed |
| Quét file đã commit tìm khóa API và email | không có |

Kết luận: mã nguồn ổn định và có kiểm thử tốt. Việc còn lại tập trung ở hai mảng: **triển khai công khai** (Phase 2 chưa bắt đầu, chưa có artifact deploy nào) và **bằng chứng cho báo cáo** (thiếu cơ sở lý thuyết, SUS, ảnh chụp giao diện mới).

## 2. Chặn deploy công khai (P1)

| ID | Phát hiện | Vị trí | Hướng xử lý |
| :--- | :--- | :--- | :--- |
| P1-1 | Danh tính người dùng là UUID do client tự sinh trong header `X-User-Id`. Repo đang **public** và `CURRENT_STATE.md` ghi UUID của hai tài khoản demo, nên nếu deploy ở chế độ hiện tại thì bất kỳ ai cũng đọc/sửa được tủ đồ demo và tiêu tiền Gemini/fal.ai không giới hạn. | `backend/app/core/dependencies.py:56-70`, `frontend/src/lib/api.ts:52-71` | Không deploy công khai trước khi xong phần xác thực phiên và quota của Phase 2. |
| P1-2 | Chưa có Dockerfile backend/frontend, `compose.prod.yaml`, reverse proxy. `compose.yaml` chỉ chạy MinIO. | gốc repo | Theo checklist Phase 2. |
| P1-3 | `alembic` chỉ nằm trong `[dev]`, nhưng khi khởi động backend bắt buộc schema ở revision `0014`. Image production cài không kèm `[dev]` sẽ không chạy được migration. | `backend/pyproject.toml:29`, `backend/app/core/database.py:59` | Chuyển `alembic` sang dependency chính, hoặc chạy migration từ một stage riêng. |
| P1-4 | Đường dẫn gắn với bố cục repo: `.env` và thư mục lưu trữ local đều tính từ `REPOSITORY_ROOT = parents[3]`. Trong container (`/app/app/core/config.py`) giá trị này là `/`, nên dữ liệu sẽ nằm ở `/data/storage` ngoài volume nếu không cấu hình. | `backend/app/core/config.py:8`, `backend/app/core/dependencies.py:48-49` | Thêm setting cho thư mục lưu trữ local, mount volume đúng chỗ. Đồng thời chốt dùng MinIO hay local: `.env` local đang dùng `local` (media đã chép sang `data/storage`), còn `.env.example` mặc định `minio`. |

## 3. Nên sửa trước khi deploy (P2)

| ID | Phát hiện | Vị trí | Hướng xử lý |
| :--- | :--- | :--- | :--- |
| P2-1 | `POST /api/v1/tryons` là request đồng bộ, có thể chạy tới `TRYON_TIMEOUT_SECONDS=90`. Nginx mặc định cắt sau 60 giây. Ingestion chạy bằng `BackgroundTasks` trong tiến trình, scheduler dọn dẹp cũng chạy trong tiến trình. | `backend/app/api/v1/endpoints/tryons.py:115-145` | Đặt timeout proxy ≥ 120 giây cho `/api/v1/tryons`; chạy **một** worker uvicorn (khớp với SQLite một tiến trình ghi). |
| P2-2 | SQLite chưa bật WAL và `busy_timeout`; ingestion nền ghi song song với chat dễ gặp `database is locked`. | `backend/app/core/database.py:41-51` | Bật `PRAGMA journal_mode=WAL` và `busy_timeout` trong listener `connect` (Phase 2 đã ghi WAL). |
| P2-3 | `ProviderError` trả chi tiết nội bộ cho client: danh sách lỗi của graph, `rec_ids`, `ranked_len`. | `backend/app/api/v1/endpoints/stylist.py:255`, `:303` | Chỉ log phía server, trả `details` rỗng hoặc chỉ `reason`. (Mục mở đã ghi trong `CURRENT_STATE.md`.) |
| P2-4 | `/docs`, `/redoc`, `/openapi.json` bật mặc định; `/api/v1/system/cleanup-metrics` không cần định danh. | `backend/app/main.py:44`, `backend/app/api/v1/endpoints/system.py` | Tắt hoặc bảo vệ ở profile production. |
| P2-5 | Upload avatar đọc toàn bộ file trước khi kiểm tra kích thước; ingestion nhận tối đa 10 ảnh × 10 MB. | `backend/app/api/v1/endpoints/tryons.py:66` | Giới hạn `client_max_body_size` ở proxy (khoảng 105 MB cho ingestion, 12 MB cho avatar) ngoài việc sửa code. |
| P2-6 | Dependency Python dùng `>=` và không có lockfile (`langgraph`, `langchain-core`, `onnxruntime`, `numpy`, ...). Build lại image có thể nhận phiên bản khác với bản đã đo. | `backend/pyproject.toml` | Xuất lockfile từ môi trường đang pass 976 test và dùng nó khi build image. |
| P2-7 | `NEXT_PUBLIC_API_URL` được nhúng lúc build, mặc định `http://localhost:8000`. | `frontend/src/lib/api.ts:41` | Truyền khi `docker build`, hoặc cho proxy phục vụ `/api` cùng origin với frontend; cách cùng origin cũng tránh vấn đề CORS và cookie `SameSite`. |

## 4. Mức nhỏ (P3)

- Lỗi ESLint ở `TryOnModal.tsx:227` làm `npm run lint` thất bại; nên sửa trước khi đưa lint vào CI hoặc build image.
- `get_detector_model()` và `get_vision_model()` trả về `"gemini-1.5-flash"` khi model trống (`backend/app/core/config.py:151`, `:163`). Model này đã ngừng; validator đã chặn trường hợp Gemini thiếu model, nên nên raise lỗi thay vì fallback.
- `Image.getdata` deprecated trong `backend/tests/unit/test_crop_boundaries.py:23` (Pillow 14).
- Bộ test backend mất khoảng 9 phút; khi đưa vào CI nên tách nhóm `evaluation`.

## 5. Tài liệu

- `ALIGNMENT_BACKLOG.md` T-2 còn ghi benchmark multi-agent nằm trên "nhánh chưa merge"; thực tế đã merge (PR #21, #22). T-1 còn ghi số test cũ (772 backend, 123 frontend). Đã cập nhật các dữ kiện này trong lần review này; phần quyết định của chủ dự án giữ nguyên.
- `docs/archive/README.md` chưa liệt kê `CHUONG_7_DANH_GIA_SO_HOA_TU_DO_NHAP_2026-11-19.md` và `LIVE_DEV_CHATBOT_ONLY_2026-11-23.md`; đã bổ sung.
- Ảnh chụp giao diện trong `docs/archive/reports/screenshots/` có từ trước đợt redesign UI; báo cáo cần chụp lại.

## 6. Sẵn sàng viết báo cáo

### 6.1. Đối chiếu 8 chương của mẫu với nguồn trong repo

| Chương mẫu | Nguồn đã có | Còn thiếu |
| :--- | :--- | :--- |
| 1. Giới thiệu | Thesis chương 1 | — |
| 2. Cơ sở lý thuyết | Gần như không có; cả repo chỉ có một link arXiv | Hệ đa tác tử và LangGraph; hệ gợi ý và độ tương thích trang phục; phát hiện đối tượng open-vocabulary (YOLO-World) và VLM trích thuộc tính; virtual try-on; LLM-as-a-judge; cá nhân hóa từ rating tường minh. Cần thu thập tài liệu tham khảo. **Đây là khoảng trống lớn nhất.** |
| 3. Phân tích yêu cầu | `PRD_MVP.md`, thesis chương 2 | Use case diagram |
| 4. Thiết kế hệ thống | `SYSTEM_ARCHITECTURE.md`, `MULTI_AGENT_SPEC.md`, `DATA_SCHEMA.md`, `API_CONTRACT.md`, `FASHION_KNOWLEDGE_BASE.md` | Quyết định T-4 (đưa mô hình 5 thuộc tính, 3 tầng vào báo cáo) |
| 5. Giải pháp công nghệ | Pipeline số hóa, detector Gemini + fallback YOLO-World, lựa chọn FLUX VTO qua spike, deadline cho provider | Quyết định T-3 (try-on là phạm vi chính hay thử nghiệm) |
| 6. Hiện thực và Triển khai | Mã nguồn, 976 + 132 test | Phase 2 (deploy) chưa làm; ảnh chụp giao diện mới |
| 7. Đánh giá và thảo luận | Xem 6.2 | SUS; độ trễ đo trên VPS; rating từ người dùng thật |
| 8. Kết luận | — | — |
| Nhật ký làm việc | 236 commit, báo cáo trong `docs/archive/` có ngày | Tổng hợp theo tuần |

Mẫu còn yêu cầu poster A0, abstract tiếng Anh/tiếng Việt và danh mục từ viết tắt.

### 6.2. Bằng chứng cho chương Đánh giá

| Tiêu chí (thesis 6.1) | Bằng chứng | Ghi chú khi viết |
| :--- | :--- | :--- |
| Chất lượng tủ đồ số | `LIVE_INGESTION_EVALUATION_2026-11-19.md`, `..._2026-11-25.md` | Gemini định vị 25/47 món, YOLO-World 17/47; độ chính xác thuộc tính giữa các detector không khác biệt có ý nghĩa |
| Chất lượng tư vấn | `MULTI_AGENT_OFFLINE_BENCHMARK_2026-11-22_v3.md`, `LIVE_MULTI_AGENT_BENCHMARK_2026-11-23.md` (+ holdout), `HUMAN_VS_JUDGE_CALIBRATION_2026-11-25.md` | Spearman người–judge 0,895, giữa các người chấm 0,946. Phải nêu các lưu ý trong `MULTI_AGENT_BENCHMARK_REVIEW_2026-11-25.md` |
| Độ sát với gu riêng | `RATING_PERSONALIZATION_SIMULATION_2026-11-25.md` | 3,17 → 3,24 sao, không có ý nghĩa thống kê; ảnh hưởng bị giới hạn ±0,02 theo thiết kế. Trình bày đúng như vậy |
| Trải nghiệm người dùng | Chưa có | SUS 5–10 người là tiêu chí duy nhất còn thiếu hoàn toàn |
| Tốc độ phản hồi | `LIVE_CHAT_LATENCY_2026-11-25.md` | p95 4,2 giây (tắt giải thích LLM) và 8,7 giây (bật); đo trên máy local |
| Thử đồ | `TRYON_PROVIDER_SPIKE_2026-11-22.md` | — |

Bảng 6.1.1 trong thesis (417/75 test, số liệu offline ngày 17/09) cần được giữ làm mốc MVP có ghi ngày, hoặc thay bằng số liệu mới (T-1).

## 7. Thứ tự đề xuất

1. **Chủ dự án chốt** T-1 đến T-4, chốt VPS, domain và quota cho Phase 2, và lên lịch buổi SUS.
2. **Sửa nhanh trong một PR nhỏ** (không đổi hành vi gợi ý): P2-3, P2-4, lỗi ESLint, P3 về model fallback.
3. **Phase 2**: xác thực phiên và quota (P1-1), sau đó Dockerfile, `compose.prod.yaml`, proxy (P1-2 đến P1-4, P2-1, P2-2, P2-5 đến P2-7), backup/restore, smoke test trên URL công khai.
4. **Song song với bước 3**: viết chương 1–5 và thu thập tài liệu cho chương 2, vì các chương này không phụ thuộc vào deploy.
5. Sau khi deploy: chạy SUS với người dùng pilot trên URL công khai, đo lại độ trễ trên VPS, chụp lại giao diện, rồi viết chương 6–7. Nếu thời gian không đủ, chạy SUS trên bản local và ghi rõ điều kiện đo.
