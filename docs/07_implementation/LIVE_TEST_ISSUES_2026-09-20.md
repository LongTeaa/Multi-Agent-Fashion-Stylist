# Báo cáo vấn đề khi kiểm thử trực tiếp — 20/09/2026

## Phạm vi và trạng thái

Báo cáo dựa trên ảnh chụp và log do người dùng cung cấp khi thao tác trên ứng dụng local: tải ảnh và kiểm duyệt món đồ, xem gợi ý phối đồ, mở try-on, tủ đồ và bộ đồ đã lưu. LT-01 đã có nguyên nhân trực tiếp từ log và đã được kiểm tra bằng một ảnh mẫu; các mục khác vẫn cần Network trace hoặc log tương ứng. Không xem ảnh màu mẫu là phép đo độ chính xác Vision trên quần áo thật.

Môi trường khi phát sinh LT-01: `VISION_PROVIDER=gemini`, `VISION_MODEL=gemini-2.5-flash`, `IMAGE_PROVIDER=gemini`, `IMAGE_MODEL=gemini-3.1-flash-image`, MinIO. Sau khi nhận log, `VISION_MODEL` trong `.env` local đã đổi thành `gemini-3.6-flash`. Không ghi API key, URL chứa key, user ID hoặc nội dung ảnh gốc vào báo cáo lỗi.

Quy ước: **P1** ảnh hưởng trực tiếp tới dữ liệu hoặc luồng chính; **P2** ảnh hưởng chất lượng kết quả/khả năng kiểm duyệt; **P3** ảnh hưởng trình bày.

## Danh sách vấn đề

### LT-01 — Vision không trả metadata hữu dụng (P1)

- **Quan sát:** Ảnh quần jean, giày và ảnh người mặc áo đều đi tới bước kiểm duyệt với `Unknown · Chưa Phân Loại`. Danh mục chính và màu chính trống. Giao diện hiển thị cảnh báo không thể tự động phát hiện/trích xuất thuộc tính và yêu cầu bổ sung thủ công.
- **Tác động:** Người dùng phải nhập lại dữ liệu cốt lõi; chất lượng truy xuất và gợi ý sau đó không thể dùng để đánh giá Vision thật.
- **Điểm code liên quan:** `backend/app/services/ingestion_service.py` tạo vùng phát hiện tạm để vẫn cho phép kiểm duyệt khi detector thất bại và thêm cảnh báo khi extractor lỗi. `backend/app/services/gemini_provider.py` gọi Gemini cho cả phát hiện và trích xuất.
- **Nguyên nhân đã xác nhận:** Log detector và extractor đều trả HTTP 404 với thông báo `gemini-2.5-flash` không còn khả dụng cho người dùng mới và yêu cầu chuyển sang `gemini-3.6-flash`. Đây là model ID không khả dụng với project hiện tại, không phải bằng chứng key hoặc định dạng request sai. Code dùng `generateContent`; Google vẫn hỗ trợ endpoint này, dù khuyến nghị Interactions API cho dự án mới.
- **Đã kiểm tra:** Sau khi đổi `VISION_MODEL=gemini-3.6-flash`, hai lời gọi live với ảnh PNG màu mẫu đều thành công: detector trả JSON hợp lệ (`input_kind=unknown`, 0 box phù hợp với ảnh không phải quần áo), extractor trả đủ nhóm khóa metadata và một cảnh báo chất lượng. Lượt tải đôi sneaker trắng sau đó đã trích xuất được category `footwear`, subtype `sneakers`, màu trắng và các thuộc tính khác; detector ở lượt này bị 503 riêng (LT-12). Điều này cho thấy lỗi 404 cũ đã hết, chưa đủ để đo độ chính xác tổng thể.
- **Kiểm chứng:** Lặp lại với một ảnh món đồ rõ nét. Ghi `batch_id`, HTTP status và thời gian của request upload/review; đối chiếu log backend đã che thông tin nhạy cảm. Phân biệt lỗi detector, lỗi extractor, timeout, phản hồi sai cấu trúc và quota/quyền truy cập model. Kiểm tra model/key với một smoke test riêng dùng ảnh mẫu không nhạy cảm.
- **Hướng giải quyết:** Khởi động lại backend để nạp `.env` mới, tải lại một ảnh quần áo thật và xác nhận kết quả. Nếu phản hồi Gemini không khớp schema thì điều chỉnh prompt/parser và thêm test từ phản hồi đã ẩn dữ liệu. Giữ đường nhập thủ công làm fallback, nhưng hiện rõ bước nào thất bại.
- **Hoàn tất khi:** Ảnh đơn đạt chất lượng tốt trả danh mục và các thuộc tính có thể kiểm duyệt; khi provider lỗi, người dùng vẫn nhập thủ công và thấy lý do ngắn gọn.

### LT-02 — Trường mặc định dễ bị hiểu là kết quả AI (P1)

- **Quan sát:** Dù món đồ chưa được phân loại, form vẫn hiển thị sẵn các giá trị như `Cotton (Bông)`, `Trơn (Solid)`, `Thường nhật (Casual)`, `Tiêu chuẩn (Regular fit)` và mức trang trọng `3/5`.
- **Tác động:** Người dùng có thể lưu metadata chưa được xác nhận như thể AI đã nhận diện được, làm sai dữ liệu tủ đồ và điểm phối đồ. Chưa xác minh server có chặn lưu danh mục trống hay không.
- **Kiểm chứng:** So sánh payload review API với trạng thái form ban đầu; thử lưu một món chưa chọn danh mục và kiểm tra phản hồi cùng bản ghi được lưu.
- **Hướng giải quyết:** Với trường thiếu hoặc không chắc chắn, hiển thị trạng thái chưa chọn; chỉ gán giá trị khi API thật sự trả về hoặc người dùng chủ động chọn. Trường bắt buộc phải được xác nhận trước khi lưu; phân biệt giá trị AI đề xuất với giá trị do người dùng nhập.
- **Hoàn tất khi:** Không có metadata suy đoán được lưu ngầm; luồng xác nhận báo rõ các trường còn thiếu.

### LT-03 — Ảnh gốc đôi lúc không hiển thị ở màn kiểm duyệt (P2)

- **Quan sát:** Trong lượt tải áo xanh/đỏ, khung `Ảnh gốc & vị trí nhận diện` hiện biểu tượng ảnh lỗi, trong khi crop món đồ vẫn hiển thị. Các lượt quần jean, giày và ảnh người mặc áo hiển thị ảnh gốc.
- **Tác động:** Không thể kiểm tra vùng phát hiện trên ảnh gốc trước khi xác nhận.
- **Kiểm chứng:** Trong DevTools Network, xem request media của ảnh gốc: URL, HTTP status, response MIME, thời điểm request và header `X-User-Id` (chỉ ghi có/không, không lưu giá trị). Đối chiếu crop và original asset trong batch, thời hạn URL và ownership. Thử refresh trang kiểm duyệt.
- **Hướng giải quyết:** Sửa đường lấy media theo nguyên nhân xác định; cho phép tải lại ảnh lỗi và hiện thông báo có thể hành động. Không chuyển asset sang public để khắc phục.
- **Hoàn tất khi:** Ảnh gốc và crop đều tải được sau upload và sau refresh, chỉ với đúng người sở hữu.

### LT-04 — Gợi ý phối đồ chưa giải thích rõ và thiếu đa dạng (P2)

- **Quan sát:** Với truy vấn đi làm văn phòng ở Hà Nội, một bộ dùng áo đỏ có ngôi sao và hiển thị khoảng `56% phù hợp`. Hai bộ trong ảnh dùng lại cùng quần jean và giày đen; đoạn giải thích có cấu trúc gần như giống nhau. Tên món `Giày Clothing đen` chưa tự nhiên.
- **Tác động:** Người dùng khó hiểu vì sao bộ được đề xuất và vì sao một lựa chọn điểm thấp vẫn xuất hiện. Metadata ở LT-01/LT-02 có thể là yếu tố ảnh hưởng nên chưa thể quy lỗi cho thuật toán xếp hạng.
- **Kiểm chứng:** Sau khi sửa metadata, lặp cùng profile, tủ đồ và truy vấn; ghi điểm từng bộ và các quy tắc đóng góp điểm. Kiểm tra lại ánh xạ tên `sub_category` và đoạn giải thích dựa trên các thuộc tính thực tế.
- **Hướng giải quyết:** Ưu tiên sửa dữ liệu đầu vào; sau đó đánh giá ngưỡng phù hợp, mức phạt sai phong cách/ngữ cảnh và độ đa dạng top-k theo đặc tả fashion scoring. Viết giải thích riêng cho từng bộ từ các lý do thật, không thêm món hoặc thuộc tính không có trong tủ đồ.
- **Hoàn tất khi:** Bộ điểm thấp được giải thích hoặc loại theo tiêu chí đã định; top-k đủ khác biệt khi tủ đồ có lựa chọn; tên món đọc tự nhiên.

### LT-05 — Try-on trả moodboard; chữ trong ảnh bị lỗi dấu (P2)

- **Quan sát:** Modal hiển thị đúng nhãn `Moodboard dự phòng`, thời gian khoảng `0,9 giây` và danh sách ba món. Chữ tiếng Việt **được vẽ bên trong ảnh moodboard** có ký tự/dấu sai, ví dụ tiêu đề `Moodboard dự phòng`. Nhãn HTML bên phải vẫn đọc được.
- **Tác động:** Kết quả fallback vẫn dùng được nhưng ảnh chia sẻ/xuất ra có chất lượng thấp. Ảnh chụp không chứng minh nguyên nhân gọi image model thất bại; với project chỉ có Free Tier, model tạo ảnh có thể không khả dụng theo tài liệu provider.
- **Điểm code liên quan:** `backend/app/services/moodboard.py` chọn `DejaVuSans.ttf` và rơi về font mặc định nếu thiếu; `backend/app/services/image_generation.py` chuyển sang moodboard khi provider lỗi hoặc quá 8 giây.
- **Kiểm chứng:** Đọc log try-on đã che key và kiểm tra `fallback_used`, `provider`, `model`, `duration_ms`. Phân biệt HTTP 4xx/quota với timeout 8 giây. Render moodboard trên cùng môi trường chạy thật, kiểm tra font được nạp và so sánh ảnh xuất ra ở kích thước gốc.
- **Hướng giải quyết:** Đóng gói font hỗ trợ tiếng Việt trong ứng dụng và nạp bằng đường dẫn cố định, thêm kiểm tra ảnh render cho chuỗi có dấu. Giữ fallback khi image model không khả dụng; chỉ gọi kết quả là `Ảnh minh họa AI` khi thực sự có ảnh model tạo.
- **Hoàn tất khi:** Chữ tiếng Việt trong file moodboard hiển thị đúng; API trả `fallback_used=true` cho fallback và `false` cho ảnh tạo thành công.

### LT-06 — Màn kiểm duyệt khó đọc trên desktop rộng (P3)

- **Quan sát:** Ở ảnh chụp cửa sổ rộng khoảng 1600 px, nội dung chính chỉ chiếm một vùng hẹp giữa màn hình; nhãn form, dòng cảnh báo và chú thích khá nhỏ.
- **Tác động:** Người dùng phải đọc nhiều trường nhỏ trong một bước vốn cần kiểm tra kỹ. Ảnh chụp đã bị thu nhỏ khi chia sẻ, nên cần đo trên trình duyệt ở zoom 100% trước khi đổi layout.
- **Kiểm chứng:** Kiểm tra tại 375 px, 768 px và desktop 1440–1600 px ở zoom 100% và 200%; đo khả năng đọc và truy cập bằng bàn phím.
- **Hướng giải quyết:** Tăng cỡ chữ tối thiểu cho nhãn/cảnh báo, độ tương phản và khoảng cách điều khiển; cân nhắc mở rộng vùng nội dung trên desktop mà vẫn giữ ảnh và form cùng lúc trong tầm nhìn.
- **Hoàn tất khi:** Các trường và cảnh báo đọc rõ ở kích thước chuẩn; không tràn ngang trên mobile.

### LT-07 — Điều hướng có nhiều thanh và nhãn khó phân biệt (P2)

- **Quan sát:** Màn tủ đồ có menu toàn ứng dụng (`Tủ đồ cá nhân`, `Đã lưu`, `Tư vấn Stylist`) và thanh chức năng riêng (`Tủ đồ của tôi`, `Số hóa trang phục mới`) ngay bên dưới. Các trang trong ảnh dùng thứ tự/kiểu menu khác nhau; tên `Đã lưu` không cho biết đó là bộ đồ đã lưu, còn `Tủ đồ của tôi` gần trùng `Tủ đồ cá nhân`. Người dùng trực tiếp báo khó hiểu và khó sử dụng.
- **Tác động:** Khó biết vị trí hiện tại, nơi thêm món, nơi xem món và nơi xem bộ đã lưu; tăng thao tác quay lại.
- **Kiểm chứng:** Đi qua luồng Tủ đồ → Thêm món → Tư vấn → Lưu bộ → Bộ đã lưu trên desktop và mobile; ghi số lần người dùng nhầm menu, trạng thái active, tab order và tên điều hướng đọc bởi screen reader.
- **Hướng giải quyết:** Dùng một menu chính nhất quán trên mọi trang với tên đích rõ (`Tủ đồ`, `Tư vấn phối đồ`, `Bộ đồ đã lưu`, `Hồ sơ`); đặt `Thêm món đồ` là hành động nổi bật trong trang Tủ đồ thay vì một menu cấp hai cạnh `Tủ đồ của tôi`. Chỉ giữ breadcrumb hoặc nút quay lại ở bước kiểm duyệt. Trạng thái đang ở trang nào phải rõ bằng chữ/`aria-current`, không chỉ màu.
- **Hoàn tất khi:** Người dùng tìm được bốn đích chính và thao tác thêm món mà không phải đoán giữa hai thanh menu; menu giữ cùng thứ tự trên các trang.

### LT-08 — Nhãn giày dép quá rộng, subtype hiện không chuẩn (P2)

- **Quan sát:** Bộ lọc và nhãn card gộp `Giày / Dép`; item giày đen có `sub_category=Clothing` nên card hiển thị `Clothing` và lời giải thích viết `Giày Clothing đen`.
- **Tác động:** Không phân biệt sneaker, giày tây, sandal, dép hoặc bốt để tính độ trang trọng và phù hợp thời tiết; tên món thiếu tự nhiên.
- **Quyết định đề xuất:** **Giữ `footwear` là category chính** vì schema, vai trò outfit và luật phối đồ hiện dùng một slot footwear. Chuẩn hóa `sub_category` bằng danh sách có kiểm soát như `sneakers`, `oxford`, `loafers`, `sandals`, `slides`, `boots`; trong UI có thể lọc nhóm `Giày`/`Dép` từ subtype. Không tách thành category cấp cao mới khi chưa có yêu cầu nghiệp vụ khác, vì sẽ phải đổi schema/API/retrieval/scoring và dữ liệu hiện có.
- **Kiểm chứng:** Kiểm tra normalizer chặn giá trị sai như `Clothing` cho footwear, cho người dùng sửa subtype khi kiểm duyệt, và thử các quy tắc office/rain với từng subtype.
- **Hoàn tất khi:** Giày đen được đặt subtype chính xác, hiển thị tên tiếng Việt rõ và scoring phân biệt loại giày phù hợp ngữ cảnh.

### LT-09 — Cảnh báo Next.js khi phát triển (P3)

- **Quan sát:** Log frontend báo `scroll-behavior: smooth` trên `<html>`, chặn HMR từ origin `192.168.56.1`, và ảnh `/images/model-lookbook.jpg` dùng `fill` nhưng thiếu `sizes`. Các request trang `GET /wardrobe`, `/saved`, `/chat` đều trả 200.
- **Tác động:** HMR có thể không hoạt động khi truy cập dev server từ origin đó; ảnh thiếu `sizes` có thể tải quá lớn. Các cảnh báo này không giải thích lỗi Vision 404.
- **Hướng giải quyết:** Chỉ thêm `allowedDevOrigins` cho host phát triển thực sự cần dùng; khai báo `sizes` phù hợp cho ảnh `fill`; khai báo thuộc tính scroll behavior theo hướng dẫn Next.js nếu tiếp tục dùng cuộn mượt.
- **Hoàn tất khi:** Dev server không còn cảnh báo trong đường truy cập dự kiến và ảnh tải đúng kích thước; không mở rộng origin tùy ý.

### LT-10 — Nhãn `Quần / Váy` dễ nhầm với `Đầm` (P2)

- **Quan sát:** Giao diện dùng `Quần / Váy` cho category `bottom`, đồng thời có category `Đầm` (`dress`). Từ `váy` không nói rõ là chân váy hay váy liền.
- **Quyết định:** Giữ category `bottom` cho quần và chân váy, `dress` cho đầm/váy liền vì hai nhánh outfit có cấu trúc khác nhau. Đổi nhãn thành `Quần / Chân váy` ở bộ lọc, card, bước kiểm duyệt và try-on; dùng `sub_category` để phân biệt jeans, quần tây, shorts, chân váy chữ A, chân váy bút chì, v.v.
- **Đã thực hiện:** Đổi nhãn ở bốn component frontend. Chưa thay đổi giá trị API/schema.
- **Hoàn tất khi:** Người dùng chọn đúng `bottom` cho chân váy và `dress` cho đầm; nhãn nhất quán ở toàn bộ luồng.

### LT-11 — Upload lỗi 500 do chạy backend với SQLite chưa migrate (P1)

- **Quan sát:** `POST /api/v1/ingestions` trả 500; log SQLite báo `no such table: orphan_media_cleanups`. Đây là lỗi trước khi gọi Vision, nên không liên quan đến model Gemini trong LT-01.
- **Nguyên nhân đã xác nhận:** Có hai file SQLite do `DATABASE_URL=sqlite:///./data/fashion_stylist.db` là đường dẫn tương đối theo thư mục chạy process. `backend/data/fashion_stylist.db` ở revision `0007`, còn `data/fashion_stylist.db` tại repo root ở revision `0005`. Backend trong lần lỗi đang dùng file thứ hai. Migration `0006` tạo bảng cleanup; `0007` thêm `not_before`.
- **Đã thực hiện:** Sao lưu file root bằng SQLite backup API thành `data/fashion_stylist.before_0007_20260920.db`; chạy `backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head` từ repo root. Đã xác nhận revision `0007`, bảng và cột `not_before` tồn tại. `.env` local đã dùng đường dẫn SQLite tuyệt đối đến file root; `alembic current` từ root và từ `backend` đều trả `0007`. Chưa kiểm thử lại upload qua UI sau migration.
- **Hướng giải quyết lâu dài:** Kiểm tra revision khi khởi động/deploy để báo lỗi cấu hình rõ ràng thay vì để request upload trả 500. Không gộp hoặc xóa hai file DB khi chưa đối chiếu dữ liệu người dùng. Đường dẫn tuyệt đối trong `.env` phải được đổi nếu di chuyển workspace sang nơi khác.
- **Hoàn tất khi:** Tải lại ảnh qua UI thành công trên đúng database, không còn 500 do thiếu bảng; restart backend/migration không tạo file SQLite thứ hai.

### LT-12 — Gemini detector trả 503 khi tải cao; extractor vẫn thành công (P2)

- **Quan sát:** Lượt tải ảnh đôi sneaker trắng tạo batch và trả review HTTP 200. Gemini detector trả HTTP 503 `UNAVAILABLE` với thông báo model đang có nhu cầu cao; bước trích xuất metadata trên crop dự phòng vẫn thành công. Giao diện hiện `Footwear · Sneakers`, màu `white` và các độ tin cậy cao, cùng cảnh báo không thể tự động phát hiện vùng vật phẩm.
- **Giải thích:** Code hiện không retry detector. Khi detector lỗi, ingestion tạo một bounding box tạm bao trùm toàn ảnh (`0,0,1,1`), rồi gửi crop đó sang Vision extractor. Với ảnh chỉ có một đôi giày, cách dự phòng này vẫn cho phép kiểm duyệt; với ảnh nhiều món, một crop toàn ảnh có thể gom sai các món thành một.
- **Kiểm chứng:** Tải lại cùng ảnh đơn sau vài phút và thử một ảnh nhiều món. Ghi riêng tỉ lệ 503, thời gian xử lý, số box và kết quả extractor; tránh kết luận 503 là lỗi key hoặc schema.
- **Hướng giải quyết:** Thêm retry giới hạn cho HTTP 503/429 ở detector với backoff ngắn và có giới hạn tổng thời gian; không retry lỗi 4xx cố định như model 404. Nếu vẫn thất bại, giữ fallback kiểm duyệt thủ công và nói rõ vùng chọn là toàn ảnh. Với ảnh nhiều món, yêu cầu người dùng tách/chỉnh vùng trước khi lưu từng món.
- **Hoàn tất khi:** 503 thoáng qua có thể tự phục hồi trong ngân sách xử lý; nếu không phục hồi, review vẫn dùng được nhưng không diễn giải vùng toàn ảnh như phát hiện vật phẩm chính xác.

### LT-13 — Trang phục cũ biến mất khỏi giao diện sau khi khởi động lại (P1)

- **Quan sát:** Người dùng báo ảnh/món đồ đã upload trước đó không còn trong giao diện sau khi chạy lại chương trình.
- **Nguyên nhân đã xác nhận:** Có hai file SQLite. Với cùng một user, `backend/data/fashion_stylist.db` có 4 wardrobe items cũ, còn `data/fashion_stylist.db` ở repo root hiện có 1 item. `.env` hiện trỏ cố định đến file root, nên API không đọc 4 item ở file `backend/data`. Frontend cũng lưu user ID trong `localStorage` theo origin; đổi giữa `localhost` và `127.0.0.1`, dùng cửa sổ ẩn danh hoặc xóa storage có thể tạo user ID mới và làm tủ đồ trông trống, nhưng đó chưa phải nguyên nhân chính của 4 item đã đối chiếu.
- **Tình trạng ảnh:** File DB cũ còn 8 liên kết `item_media` cho 4 item; cả 8 object tương ứng đều còn trong MinIO. MinIO đang chạy với volume. Đây là vấn đề chọn database, không phải ảnh đã bị xóa khỏi object store.
- **Hướng giải quyết:** Sao lưu cả hai SQLite trước khi hợp nhất. Chọn một database chuẩn, chuyển các item cũ cùng quan hệ media và metadata phụ thuộc sang database chuẩn theo một giao dịch có kiểm tra khóa ngoại và chống trùng ID; không đổi `.env` qua lại vì sẽ chỉ hoán đổi tập item hiển thị. Sau khi hợp nhất, xác minh số item của cùng user và truy cập ảnh qua API private. Về lâu dài, dùng một đường dẫn SQLite cố định và hiển thị rõ danh tính demo/current workspace trong UI; giữ ổn định origin frontend khi test.
- **Hoàn tất khi:** Cùng một user thấy cả 4 item cũ và item mới sau restart; từng thumbnail/crop tải được; không có item trùng hoặc media bị gán sai user.

**Cập nhật 24/09/2026:** `backend/scripts/merge_wardrobe_databases.py` hỗ trợ dry run và import có sao lưu hai SQLite, chạy trong một giao dịch, kiểm tra khóa ngoại và chạy lại không nhân đôi bản ghi. Trên máy kiểm thử, đã nhập 4 wardrobe items, 8 item-media links và các batch/detection/media/retrieval records phụ thuộc từ `backend/data/fashion_stylist.db` vào `data/fashion_stylist.db`. Dry run sau import báo 0 bản ghi thiếu. Chạy lại ứng dụng với cùng user/origin và kiểm tra ảnh qua API private vẫn cần thực hiện khi MinIO và frontend hoạt động.

Lệnh cho môi trường có cùng hai file SQLite (dừng API và cleanup scheduler trước khi dùng `--apply`):

```text
python backend/scripts/merge_wardrobe_databases.py backend/data/fashion_stylist.db data/fashion_stylist.db
python backend/scripts/merge_wardrobe_databases.py backend/data/fashion_stylist.db data/fashion_stylist.db --apply
```

## Thứ tự xử lý đề xuất

1. Giải quyết LT-13 để người dùng thấy cùng một tủ đồ qua các lần chạy; sao lưu và đối chiếu dữ liệu trước khi hợp nhất. Lượt tải sneaker đã xác nhận đường upload qua lỗi thiếu bảng LT-11 và lỗi model 404 LT-01.
2. Ổn định đường dẫn database để LT-11 không tái diễn. Thu Network trace và log cho LT-03, LT-05. Sửa LT-02 và kiểm thử lại upload → kiểm duyệt → lưu với ảnh đơn rõ nét.
3. Sửa LT-03 để người dùng kiểm chứng crop trên ảnh gốc.
4. Đánh giá lại LT-04 sau khi dữ liệu tủ đồ đã chính xác.
5. Sửa font LT-05 và kiểm thử fallback cùng nhánh image model thật khi project có quyền truy cập.
6. Đơn giản hóa điều hướng LT-07, chuẩn hóa footwear subtype LT-08, xác nhận nhãn LT-10 và cải thiện LT-06 trên các viewport.
7. Xử lý các cảnh báo dev LT-09 sau các lỗi ảnh hưởng luồng chính.

## Tiêu chí chạy lại toàn luồng

- Upload ảnh đơn và ảnh nhiều món; xác nhận không lưu món AI bịa hoặc metadata mặc định chưa được chấp thuận.
- Xem ảnh gốc/crop qua media private với đúng tài khoản; tài khoản khác không truy cập được.
- Nhận gợi ý chỉ từ các món đang hoạt động trong tủ đồ, kiểm tra điểm và lý do chọn bộ.
- Try-on trả ảnh minh họa hoặc moodboard đúng nhãn; fallback thành công khi provider lỗi; chữ tiếng Việt trong ảnh đúng dấu.
- Ghi model, thời điểm và thời gian phản hồi cho lần chạy live; giữ test giả lập làm bộ kiểm tra hồi quy.

Các điều kiện chuẩn vẫn do `PRD_MVP.md`, `API_CONTRACT.md`, `DATA_SCHEMA.md` và `VIRTUAL_TRYON_SPEC.md` quy định; báo cáo này chỉ theo dõi vấn đề phát hiện trong lần kiểm thử trực tiếp.

Tài liệu provider dùng để kiểm tra LT-01: [Gemini 3.6 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash) và [Interactions API overview](https://ai.google.dev/gemini-api/docs/interactions-overview). API `generateContent` hiện vẫn được hỗ trợ, dù được xem là giao diện cũ.
