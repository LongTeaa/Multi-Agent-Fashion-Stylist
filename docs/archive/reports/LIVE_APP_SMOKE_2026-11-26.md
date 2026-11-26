# Chạy thử trực tiếp ứng dụng — 2026-11-26

Chạy ứng dụng thật trên máy local tại `main` `bf3b6fe`, điều khiển giao diện bằng Playwright (Chromium headless) như một người dùng, không dùng bộ test tự động. Mục đích: kiểm tra các luồng chính với provider thật trước khi viết báo cáo và deploy.

## 1. Cấu hình

| Thành phần | Giá trị |
| :--- | :--- |
| Backend | `uvicorn app.main:app` cổng 8000, `.env` local: Gemini detector với YOLO-World dự phòng, `gemini-3.6-flash` cho vision và context, Open-Meteo, FLUX VTO, lưu trữ local, `ENABLE_LLM_EXPLANATIONS` tắt |
| Database | Bản sao `data/fashion_stylist.livetest_20261126.db` của database demo, để không thay đổi tủ đồ demo |
| Frontend | `next dev` cổng 3000 |
| Tài khoản | Demo nữ, demo nam và một tài khoản mới tạo trong lần chạy |
| Ảnh tải lên | `images_bayra5.jpg` (2 món trải phẳng) và `images_nguyenbo1.jpg` (bộ đang mặc) trong `data/private-vision-review/real_img` |

## 2. Kết quả theo luồng

| Luồng | Kết quả | Số đo |
| :--- | :--- | :--- |
| 5 trang (`/`, `/wardrobe`, `/chat`, `/saved`, `/profile`) | Đạt: không lỗi console, không lỗi API, không ảnh hỏng, không tràn ngang | Tải trang 2,6–4,2 s (dev server) |
| Số hóa tủ đồ qua giao diện | Đạt: 2 ảnh cho 7 món, duyệt rồi lưu đủ 7 món | 25,6 s từ lúc tải lên đến màn hình duyệt |
| Chat, Gemini và Open-Meteo hoạt động | Đạt: nhận đúng dịp, ngày, địa điểm, nhiệt độ từ API (19,7 °C), hồ sơ `formal`; 3 bộ đồ, mọi món thuộc tủ đồ của người dùng | 6,5 s; 1,6–2,6 s trên tủ đồ 7 món |
| Chat khi Gemini lỗi | Đạt: luật dự phòng trả 3 bộ đồ và cảnh báo | 1,0 s |
| Câu hỏi mơ hồ "Mặc gì?" | Đạt: hỏi lại một câu tiếng Việt, không trả gợi ý | 2,6 s |
| Lưu, đã mặc, chấm 5 sao trên thẻ | Đạt: API xác nhận `is_bookmarked`, `times_worn = 1`, `user_rating = 5` | |
| Chu kỳ hỏi đánh giá | Đạt: lời mời xuất hiện sau 9 bộ đồ (trong khoảng 5–10), chấm qua lời mời trả 200 | |
| Trang Đã lưu, chấm lại 3 sao | Đạt | |
| Lưu gu ở trang hồ sơ | Đạt: API trả đúng lựa chọn, giữ nguyên sau khi tải lại | |
| Cô lập dữ liệu | Đạt: outfit, item, rating, xóa item của người khác trả 404; media trả 403; thiếu `X-User-Id` trả 422; dữ liệu người kia không đổi | |
| Mặc thử FLUX VTO | **Không đạt trên mạng này**: cả 2 lần đều về moodboard dự phòng (`PROVIDER_FAILED`), API vẫn trả 200 với `fallback_used = true` đúng đặc tả | 9,6–12,2 s |

## 3. Vấn đề phát hiện

### 3.1. Môi trường

- **Mặc thử thất bại do DNS của mạng local.** DNS `10.30.3.38` không phân giải được `v3.fal.media` (CDN chứa ảnh kết quả của fal.ai), trong khi DNS công khai phân giải bình thường (`v3b.fal.media`, `178.249.208.249`). Lệnh gọi tới `fal.run` vẫn diễn ra nên có thể vẫn bị tính phí, chỉ bước tải ảnh kết quả thất bại. Trên VPS ở nước ngoài hoặc với DNS công khai, lỗi này có thể không xảy ra; cần chạy lại để xác nhận.
- Lần chat đầu tiên Gemini lỗi và hệ thống dùng luật dự phòng. Không xác định được nguyên nhân vì lỗi không được ghi log (mục 3.2).

### 3.2. Code và vận hành

- `backend/app/agents/context_agent.py:926` bắt `except Exception:` mà không ghi log, nên không biết vì sao Gemini thất bại. Trước khi deploy nên ghi ít nhất loại exception.

### 3.3. Chất lượng gợi ý (do dữ liệu)

- **Yêu cầu trang trọng vẫn ra quần jeans.** Với "phỏng vấn ở công ty" (mức 4–5), tài khoản demo nam nhận sơ mi + jeans + boots ở hạng 1 (0,7498), trên bộ sơ mi + quần tây + blazer (0,7247). Nguyên nhân là dữ liệu: quần tây của tủ demo nam được gắn mức trang trọng 1–2 và sơ mi mức 2, ngang jeans; chỉ blazer đạt mức 4. **Cần rà lại thuộc tính tủ đồ demo trước buổi bảo vệ.**
- Với tủ đồ mới, đôi boots duy nhất bị gắn trang trọng 1/5. Quy tắc món lệch xa nhất (weakest link) làm mọi bộ có cùng điểm trang trọng, nên quần tây không được ưu tiên cho "ăn tối với đối tác" hay "đi làm văn phòng".
- Hai gợi ý hiển thị giống hệt nhau ("Áo sơ mi trắng, Quần jeans xanh dương, Giày boots đen") vì tủ có hai áo sơ mi trắng khác nhau; người dùng không phân biệt được.

### 3.4. Giao diện

- Màn hình duyệt hiện giá trị tiếng Anh thô: "Loại món: shirt", "Màu sắc chủ đạo: white", tiêu đề "Áo · Shirt".
- Thẻ tủ đồ hiện màu `charcoal`, `dark_gray` bằng tiếng Anh và tên "Tie" cho cà vạt.
- Moodboard dự phòng ghi nhãn tiếng Anh: "BOTTOM culottes", "FOOTWEAR flats", "TOP turtleneck".
- Giày và mũ hiện thuộc tính chiều dài vô nghĩa ("Ngang eo", "Lửng (Cropped)"), dù `FASHION_KNOWLEDGE_BASE.md` §2.4 nói chiều dài không dùng cho giày và phụ kiện.
- Hộp thoại mặc thử mặc định chọn "Nam mẫu" cho bộ đồ của tài khoản nữ.
- Lời mời chấm sao nổi đè lên một phần thẻ Look 01 ở màn hình rộng 1280 px.
- Ảnh crop áo sơ mi từ ảnh đang mặc dính cằm và miệng người mẫu; crop đôi boots rất nhỏ.

## 4. Đã sửa sau lần chạy

Sửa cùng ngày, kiểm tra lại trên ứng dụng đang chạy (vision, detector, context giả; try-on tắt, nên không tốn phí):

| Vấn đề | Sửa | Kiểm tra trên ứng dụng |
| :--- | :--- | :--- |
| Lỗi Gemini không ghi log | `context_agent.py` ghi cảnh báo kèm loại exception, không ghi câu hỏi | Unit test |
| Màn hình duyệt hiện `shirt`, `white` | Hiện `Áo Polo`, `Trắng`; vẫn lưu giá trị chuẩn; nhập nhãn tiếng Việt được đổi về giá trị chuẩn | Tiêu đề và ô nhập hiện tiếng Việt |
| Màu và cà vạt tiếng Anh | Thêm nhãn màu (`charcoal`, `dark_gray`, `teal`, `light blue`…) ở frontend và backend; thêm loại `tie` (Cà vạt), `scarf` (Khăn quàng) | Thẻ hiện `Cà Vạt`, `Xám đậm`, `Xám than` |
| Moodboard ghi `BOTTOM culottes` | Slot, loại và màu bằng tiếng Việt | Moodboard hiện `QUẦN / CHÂN VÁY · Quần tây · Trắng` |
| Chiều dài trên giày và phụ kiện | Ẩn trên thẻ tủ đồ và trong form sửa | Thẻ giày boots và cà vạt không còn chiều dài |
| Người mẫu nam cho bộ váy liền | Nhớ người mẫu đã chọn; bộ có váy liền mở với người mẫu nữ | Yêu cầu try-on gửi `preset-female` |
| Lời mời chấm sao che bộ cuối | Thêm khoảng đệm cuối trang khi lời mời hiện | Hàng sao của bộ cuối không bị che ở 1280 px và 375 px |

Chưa sửa: dữ liệu trang trọng của tủ đồ demo (mục 3.3), lỗi DNS (mục 3.1), crop dính mặt và crop quá nhỏ (mục 3.4).

## 5. Chưa kiểm tra

- Mặc thử thành công với FLUX VTO và mặc thử trên ảnh toàn thân tự tải lên, vì lỗi DNS ở mục 3.1.
- Giải thích bằng LLM (`ENABLE_LLM_EXPLANATIONS=true`).
- Sửa vùng crop và sửa thuộc tính trên màn hình duyệt.

Ảnh chụp màn hình và script điều khiển được giữ ngoài repo vì chứa ảnh tủ đồ riêng của nhóm.
