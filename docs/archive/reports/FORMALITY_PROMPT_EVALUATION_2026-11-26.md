# Thang trang trọng trong prompt vision — 2026-11-26

## 1. Vấn đề

Khi chạy thử ứng dụng (`LIVE_APP_SMOKE_2026-11-26.md`), tủ đồ demo nam đề xuất quần jeans cho buổi phỏng vấn. Nguyên nhân nằm ở dữ liệu: 31/32 món nam và 31/31 món nữ giữ nguyên mức trang trọng do Gemini đề xuất lúc số hóa, và các mức này thấp hơn thang của `../../03_domain/FASHION_KNOWLEDGE_BASE.md` §2.1 khoảng một bậc (áo thun, sneaker, quần short ở mức 1; polo ở mức 2; sơ mi dài tay ở mức 2–3).

Prompt vision chỉ định nghĩa thang bằng ba mốc: `1=very casual/loungewear, 3=smart casual, 5=strictly formal/black tie`. Mức 2 và 4 không có mô tả, và không có ví dụ nào khớp với các mốc mà agent chấm điểm sử dụng. Trên bộ gold 58 ảnh, mọi lỗi trang trọng của lần chạy 2026-11-25 đều thấp hơn đáp án.

Hai chốt kiểm tra không bắt được lỗi này:

- **Màn hình duyệt:** mức trang trọng nằm trong "Chi tiết bổ sung" (thu gọn có chủ đích để người dùng ít phải sửa) và chỉ được đánh dấu khi độ tin cậy thấp; Gemini trả độ tin cậy 0,9–1,0.
- **Gold v1:** chấm theo "thang 1–5 của prompt vision" và có cùng độ lệch ở mức thấp (sneaker, quần short dạo phố, mũ ở mức 1). Chỉ số "lệch không quá một mức" bằng 100% nên không lộ ra một độ lệch có hệ thống đúng một bậc.

## 2. Thay đổi

| Thành phần | Thay đổi |
| :--- | :--- |
| Prompt | `FORMALITY_SCALE_PROMPT` trong `backend/app/services/gemini_provider.py` định nghĩa đủ 5 mức, mỗi mức có ví dụ lấy từ `FASHION_KNOWLEDGE_BASE.md` §2.1, cùng quy tắc chất liệu/kiểu dáng thường ngày giảm một bậc, cắt may sắc nét tăng một bậc. Test: `backend/tests/unit/test_vision_formality_prompt.py` |
| Gold | `data/fixtures/vision_attribute_gold_v2.json`: giống v1, chỉ đổi 11 nhãn trang trọng từ 1 lên 2 (demo-14, 28, 30, 32, 41, 46, 47, 53, 56, 57, 58: sneaker, quần short dạo phố, áo thun graphic, áo thể thao, mũ). Các nhãn này do coding agent đề xuất từ ảnh và §2.1, có provenance `kb_scale_proposed`, **chờ chủ dự án xác nhận**. v1 giữ nguyên |

## 3. Kết quả

Cùng cấu hình (Gemini detector + `gemini-3.6-flash`, 58 ảnh một món), chấm theo gold v2:

| Chỉ số | Prompt cũ (chạy 2026-11-25) | Prompt mới (chạy 2026-11-26) |
| :--- | :---: | :---: |
| Trang trọng đúng chính xác | 35/58 = 60,3% | **50/58 = 86,2%** (50/57 = 87,7% khi bỏ ca timeout) |
| Lệch không quá một mức | 58/58 | 57/57 trả lời |
| MAE | 0,397 | **0,123** |
| Sai số có dấu trung bình | −0,397 | **−0,018** |
| Hướng lỗi | 23 thấp hơn, 0 cao hơn | 4 thấp hơn, 3 cao hơn |
| Category | 57/58 | 56/58 |
| Loại món | 52/58 | 53/58 |
| Màu chính | 54/58 | 54/58 |
| Họa tiết | 56/58 | 53/58 |
| Ảnh lỗi vision | 0 | 1 (`demo-11`, `TimeoutError`) |
| Độ trễ trung vị | 11,6 s | 13,9 s |

Kiểm định McNemar chính xác trên cùng 58 ảnh: trang trọng đúng chính xác có 19 ảnh chỉ đúng với prompt mới và 4 ảnh chỉ đúng với prompt cũ, **p = 0,0026**. Báo cáo `LIVE_INGESTION_EVALUATION_2026-11-25.md` ghi nhận một cấu hình dao động tới 6 ảnh giữa hai ngày (p = 0,146); mức cải thiện lần này là 15 ảnh. Các trường khác không khác biệt có ý nghĩa: họa tiết 3 so với 0 (p = 0,25, trong đó một ảnh là ca timeout), loại món 2 so với 3, màu 1 so với 1.

Bảy ảnh còn sai: demo-18 (đầm hoa, 3 → 2), demo-22 (áo bomber, 3 → 2), demo-25 (blazer lửng, 4 → 3), demo-39 (sơ mi dài tay, 4 → 3), demo-27 (dép quai ngang, 1 → 2), demo-33 (áo thun sọc, 2 → 3), demo-42 (quần thể thao, 1 → 2).

Chấm theo gold v1, prompt mới chỉ đạt 39/58, thấp hơn prompt cũ (44/58). Điều này là dự kiến: v1 dùng thang của prompt cũ.

## 4. Lưu ý khi đưa vào báo cáo

- Prompt mới và gold v2 cùng lấy mốc từ §2.1. Phép đo này cho biết hệ thống số hóa **tuân theo thang của tài liệu tri thức** đến đâu, không phải độ chính xác so với một chuẩn thời trang độc lập.
- 11 nhãn của gold v2 do coding agent đề xuất và chưa được người xác nhận; báo cáo MUST NOT gọi chúng là nhãn của chuyên gia.
- Mỗi prompt chỉ chạy một lần. Kết quả ổn định của prompt mới chưa được đo bằng lần lặp cùng ngày.
- Tủ đồ demo nam đã được sửa tay ngày 2026-11-26 (21 món, theo ảnh và §2.1). Tủ đồ demo nữ được đưa về đúng nhãn gold v2 cùng ngày: mỗi món được ghép với ảnh gold qua SHA-256 của ảnh gốc (31/31 khớp); 16 món tăng một bậc trang trọng, 6 món đổi sang loại món có trong taxonomy và trong danh sách chấp nhận của gold (`mini_skirt`, `sweater`, `formal_dress`, `dress`, `casual_dress`, `joggers`).
- Sau khi sửa, câu "phỏng vấn ở công ty" vẫn xếp đầm dạ hội đính kim sa của tủ đồ nữ ở hạng 1, vì đầm này đúng mức 4 và mô hình chỉ phân biệt dịp bằng mức trang trọng, không tách tiệc tối khỏi công sở. Đây là giới hạn của mô hình chấm điểm, không phải của dữ liệu.

## 5. Tái lập

```powershell
python backend/scripts/evaluate_live_ingestion.py --live --detector gemini --gold data/fixtures/vision_attribute_gold_v2.json --out data/fixtures/live_ingestion_attributes_v2_gemini_20261126.json
python backend/scripts/evaluate_live_ingestion.py --score data/fixtures/live_ingestion_attributes_v1_gemini_20261125.json data/fixtures/live_ingestion_attributes_v2_gemini_20261126.json --gold data/fixtures/vision_attribute_gold_v2.json --metrics-out docs/archive/reports/FORMALITY_PROMPT_EVALUATION_2026-11-26.json
```

Lệnh thứ hai chạy offline. Số liệu máy đọc nằm trong `FORMALITY_PROMPT_EVALUATION_2026-11-26.json`.
