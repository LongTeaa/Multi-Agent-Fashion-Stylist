# Báo Cáo Thực Nghiệm Bước 0: Thử Đồ Ảo FASHN VTON v1.5 (Spike Report)

Tài liệu này ghi nhận kết quả nghiên cứu và thực nghiệm kiểm chứng (Spike) tính khả thi của mô hình 2D Virtual Try-On **FASHN VTON v1.5** khi kết hợp với kho đồ số hóa và ảnh người dùng trong dự án *Multi-Agent Fashion Stylist*.

---

## 1. Mục Tiêu Thực Nghiệm

1. Kiểm tra khả năng ghép trang phục của mô hình FASHN VTON v1.5 (dựa trên kiến trúc MMDiT đa phương thức khuếch tán không gian pixel) khi đầu vào là ảnh cắt (crop) thực tế từ cơ sở dữ liệu tủ đồ.
2. Đo lường các chỉ số vận hành: độ trễ inference, tiêu hao tài nguyên phần cứng (VRAM/RAM), độ phân giải đầu ra và chất lượng giữ form/chi tiết hoa văn.
3. Xác định các ràng buộc kỹ thuật và giới hạn của mô hình (ví dụ: hạn mức quota ZeroGPU, khả năng ghép giày và phụ kiện).
4. Đưa ra kết luận kỹ thuật (GO / NO-GO) và các yêu cầu kiến trúc bắt buộc cho các bước triển khai tiếp theo.

---

## 2. Kết Quả Thực Nghiệm Trực Tiếp (Live Spike)

Thực nghiệm được thực hiện trực tiếp trên Hugging Face ZeroGPU Space (`fashn-ai/fashn-vton-1.5`) thông qua thư viện `gradio_client`:

- **Ảnh người mẫu đầu vào:** Ảnh toàn thân chuẩn ($452 \times 563\text{ px}$, $120 \times 240\text{ px}$).
- **Ảnh trang phục đầu vào:** Ảnh crop thực tế chiếc áo thun từ cơ sở dữ liệu `wardrobe-private` của dự án (`real_wardrobe_crop_top.png`, kích thước $211 \times 224\text{ px}$).
- **Thời gian xử lý (Pass 1 - Top):** **36.78 giây** (chạy tại chế độ `num_timesteps=30`, `guidance_scale=1.5`).
- **Đầu ra:** Ảnh WebP độ phân giải cao ($576 \times 717\text{ px}$), đường viền cổ áo và nếp gấp tự nhiên, không xuất hiện hiện tượng biến dạng khuôn mặt hay lem màu.
- **Tiêu hao phần cứng cục bộ:** **0 MB VRAM** (quá trình tính toán diễn ra hoàn toàn trên cloud worker ZeroGPU).

---

## 3. Các Giới Hạn Kỹ Thuật Phát Hiện & Giải Pháp Kiến Trúc

Qua kiểm chứng thực nghiệm, hệ thống đã phát hiện 3 rủi ro/giới hạn kỹ thuật then chốt và đưa ra giải pháp kiến trúc tương ứng:

### A. Rủi ro giới hạn hạn mức (ZeroGPU Runs Limit)
- **Thực tế:** Khi gọi ở chế độ ẩn danh (không có token), ZeroGPU giới hạn ~70 giây GPU/ngày. Lần gọi thứ 2 (ghép quần) lập tức trả về lỗi `AppError: You have exceeded your ZeroGPU runs limit`.
- **Quy tắc bắt buộc (INVARIANT):**
  1. Hệ thống **MUST** hỗ trợ cấu hình biến môi trường `HF_TOKEN` để người dùng cung cấp Hugging Face Access Token tăng hạn mức.
  2. Hệ thống **MUST** triển khai cơ chế lưu đệm kết quả (Cache) dựa trên mã băm SHA-256 của `(user_id, avatar_id, sorted_item_ids)`. Khi người dùng thử lại cùng một bộ đồ trên cùng người mẫu, kết quả trả về ngay trong 0ms mà không tiêu tốn thêm quota GPU.
  3. Hệ thống **MUST** có cơ chế tự động chuyển đổi dự phòng (Deterministic Moodboard Fallback). Khi gặp lỗi `429`, lỗi quá quota hoặc lỗi mạng, hệ thống chuyển sang trả về bảng phối đồ Moodboard mà không làm gián đoạn trải nghiệm người dùng hay gây lỗi trắng trang.

### B. Giới hạn danh mục mô hình (Phụ kiện & Giày dép)
- **Thực tế:** Mô hình FASHN VTON v1.5 chỉ hỗ trợ tham số `category` trong 3 giá trị: `tops`, `bottoms`, `one-pieces`. Mô hình không hỗ trợ inpainting giày dép hoặc phụ kiện (đồng hồ, túi xách, kính) lên cơ thể.
- **Quy tắc bắt buộc (INVARIANT):**
  1. Quy trình inpainting cơ thể **MUST** chỉ gửi các món thuộc nhóm áo, quần hoặc đầm.
  2. Phụ kiện và giày dép **MUST** được trình bày theo phương án tọa độ đồng bộ bên cạnh người mẫu (Side-by-side Coordinates) trong giao diện để người dùng có cái nhìn toàn diện về outfit hoàn chỉnh.

### C. Xử lý nhiều lớp áo (Top + Outerwear Layering)
- **Thực tế:** Khi một bộ đồ gợi ý có cả áo trong (sơ mi, áo thun) và áo khoác ngoài (blazer, jacket), mô hình chỉ ghép 1 lớp áo trên người ở mỗi pass.
- **Quy tắc bắt buộc (SHOULD):**
  1. Hệ thống **SHOULD** mặc định ướm áo khoác ngoài để thể hiện phong cách layer đặc trưng.
  2. Giao diện **MUST** cung cấp nút chuyển đổi nhanh (Layering Toggle) cho phép người dùng chọn xem trước áo khoác ngoài hoặc áo trong tùy ý.

---

## 4. Kết Luận (Decision)

- **Kết luận:** **GO (Chính thức thông qua)**.
- **Đánh giá phạm vi luận văn:** Mô hình 2D Virtual Try-On dựa trên MMDiT Diffusion đáp ứng xuất sắc nhu cầu trực quan hóa trang phục trong đồ án tốt nghiệp, vượt trội hơn so với phương án 3D Mesh (đòi hỏi quét thể tích phức tạp) hoặc AR webcam thời gian thực (yêu cầu cấu hình máy khách lớn và đường truyền cao).
