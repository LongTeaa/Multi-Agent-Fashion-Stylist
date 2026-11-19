# Bản nháp — Chương 7. Đánh giá và thảo luận

## 7.x. Đánh giá luồng số hoá tủ đồ với dịch vụ nhận diện thật

> Bản nháp để đưa vào Chương 7 của khoá luận (mẫu "Mau bao cao KLTN_DS"). Số liệu lấy từ
> báo cáo kỹ thuật `LIVE_INGESTION_EVALUATION_2026-11-19.md`; mọi con số có thể tính lại
> từ các file kết quả thô trong `data/fixtures/`. Đánh số hình, bảng cần chỉnh theo vị trí
> thực tế trong cuốn báo cáo.

### 7.x.1. Mục tiêu đánh giá

Các số liệu nghiệm thu trước đây của hệ thống được đo bằng các thành phần giả lập
(fake provider), nên chưa phản ánh chất lượng thực tế khi ứng dụng chạy với mô hình thật.
Phần này đánh giá luồng số hoá tủ đồ đang triển khai, gồm ba bước: (1) phát hiện vùng của
từng món đồ trong ảnh, (2) cắt ảnh theo vùng phát hiện, (3) nhận diện thuộc tính của món
đồ từ ảnh đã cắt. Hai câu hỏi cần trả lời:

1. Hệ thống nhận diện đúng loại đồ, màu sắc, hoạ tiết, chất liệu và mức độ trang trọng đến
   đâu?
2. Bộ phát hiện vùng tách được từng món trong ảnh nhiều món hoặc ảnh người đang mặc tốt
   đến đâu?

### 7.x.2. Cấu hình hệ thống được đánh giá

- Bộ phát hiện vùng: YOLO-World (`yolov8s-worldv2`, chạy cục bộ dạng ONNX, ngưỡng tin cậy
  0,25).
- Bộ nhận diện thuộc tính: Gemini `gemini-3.6-flash` (mô hình dự phòng
  `gemini-3.5-flash-lite`), thời gian chờ tối đa 30 giây.
- Ảnh được đưa qua đúng dịch vụ số hoá của ứng dụng trong một cơ sở dữ liệu và kho lưu trữ
  tạm thời, tách biệt hoàn toàn khỏi dữ liệu thật. Mỗi lần gọi dịch vụ bên ngoài đều được
  ghi lại kết quả, thời gian và lỗi (nếu có).
- Kế hoạch ban đầu có so sánh với bộ phát hiện vùng của Gemini. Lượt chạy này không hoàn
  thành do vượt hạn mức sử dụng của gói miễn phí (mục 7.x.6), nên không được dùng để so
  sánh.

### 7.x.3. Dữ liệu đánh giá

**Bảng 7.1.** Các tập dữ liệu đánh giá

| Tập | Nội dung | Nhãn chuẩn |
| :--- | :--- | :--- |
| A | 58 ảnh một món đồ (trải phẳng hoặc treo), từ bộ dữ liệu mở CC0 *Clothing dataset* | Loại đồ, nhóm đồ, kiểu đồ, màu chính, hoạ tiết, chất liệu, mức trang trọng 1–5 |
| B | 14 ảnh thực tế: 5 ảnh nhiều món trải phẳng, 5 ảnh người đang mặc, 4 ảnh đồ treo móc | 47 khung bao quanh từng món, số món kỳ vọng của mỗi ảnh |
| C | 7 ảnh thực tế riêng tư từ các đợt kiểm thử trước | 10 khung, 5 ảnh có số món kỳ vọng |

Nhãn loại đồ của tập A lấy từ nhãn gốc do người gán của bộ dữ liệu. Các thuộc tính còn lại
được soạn nháp, sau đó tác giả duyệt và sửa từng ảnh bằng một công cụ gán nhãn riêng, trong
đó kết quả của hệ thống được ẩn đi để không ảnh hưởng người duyệt. Các xác nhận món đồ đã
lưu trong ứng dụng **không** được dùng làm nhãn chuẩn, vì chúng trùng với đề xuất của mô
hình ở 59/60 món. Nếu dùng chúng thì kết quả sẽ là đánh giá mô hình bằng chính đầu ra của
nó.

Với những thuộc tính có nhiều cách gọi hợp lý, nhãn chuẩn liệt kê mọi giá trị chấp nhận
được (ví dụ màu xanh cổ vịt được tính là xanh dương hoặc xanh lá). Đầu ra dạng văn bản tự
do của mô hình được chuẩn hoá về 13 màu, 9 loại hoạ tiết và 8 nhóm chất liệu của hệ thống
trước khi so sánh. Nhóm đồ và kiểu đồ được xác định bằng chính bộ phân loại của ứng dụng,
nên phản ánh đúng những gì người dùng thấy.

### 7.x.4. Phương pháp và chỉ số

- **Độ chính xác thuộc tính** = số ảnh có giá trị dự đoán nằm trong danh sách chấp nhận /
  tổng số ảnh. Lần gọi dịch vụ bị lỗi được tính là sai.
- **Mức trang trọng:** tỉ lệ đúng tuyệt đối, tỉ lệ lệch không quá 1 mức, và sai số tuyệt
  đối trung bình

  $$\text{MAE} = \frac{1}{n}\sum_{i=1}^{n} \lvert \hat{f}_i - f_i \rvert$$

- **Định vị khung:** một khung chuẩn được tính là phát hiện đúng khi ghép được một-một với
  một khung dự đoán thoả mãn đồng thời

  $$\text{IoU} = \frac{|B_{gt} \cap B_{pred}|}{|B_{gt} \cup B_{pred}|} \ge 0{,}5
  \quad\text{và}\quad \frac{|B_{gt} \cap B_{pred}|}{|B_{gt}|} \ge 0{,}9 .$$

  Điều kiện thứ hai bảo đảm ảnh cắt giữ lại ít nhất 90% món đồ. Kết quả cũng được báo cáo
  theo điều kiện chỉ cần IoU ≥ 0,5.
- Các tỉ lệ được trình bày kèm khoảng tin cậy 95% theo phương pháp Wilson, vì cỡ mẫu nhỏ.

### 7.x.5. Kết quả

**Bảng 7.2.** Độ chính xác nhận diện thuộc tính trên tập A (58 ảnh, YOLO-World + Gemini)

| Thuộc tính | Đúng | Độ chính xác | KTC 95% |
| :--- | :---: | :---: | :---: |
| Loại đồ (6 lớp) | 56/58 | 96,6% | 88,3–99,0% |
| Nhóm đồ hiển thị (8 nhóm) | 54/58 | 93,1% | 83,6–97,3% |
| Kiểu đồ | 46/58 | 79,3% | 67,2–87,7% |
| Màu chính | 51/58 | 87,9% | 77,1–94,0% |
| Hoạ tiết (9 loại) | 54/58 | 93,1% | 83,6–97,3% |
| Chất liệu (mức hợp lý khi nhìn) | 53/58 | 91,4% | 81,4–96,3% |
| Mức trang trọng, đúng tuyệt đối | 33/58 | 56,9% | 44,1–68,8% |
| Mức trang trọng, lệch ≤ 1 mức | 57/58 | 98,3% | 90,9–99,7% |

Sai số tuyệt đối trung bình của mức trang trọng là 0,42; sai số có dấu trung bình là −0,35,
tức mô hình có xu hướng đánh giá món đồ kém trang trọng hơn khoảng một phần ba mức. Thời gian
xử lý trung vị của một ảnh là 5,6 giây (90% số ảnh dưới 13,9 giây), phần lớn là thời gian
gọi Gemini; bản thân YOLO-World chỉ mất khoảng 0,2–0,3 giây.

**Bảng 7.3.** Kết quả định vị từng món đồ của YOLO-World

| Tập / loại ảnh | Phát hiện đúng (IoU ≥ 0,5 và giữ ≥ 90%) | Chỉ yêu cầu IoU ≥ 0,5 | Đúng số món |
| :--- | :---: | :---: | :---: |
| B — toàn bộ 14 ảnh | 17/47 (36,2%) | 26/47 (55,3%) | 5/14 |
| B — ảnh nhiều món trải phẳng | 8/27 (29,6%) | 9/27 (33,3%) | 1/5 |
| B — ảnh người đang mặc | 8/15 (53,3%) | 13/15 (86,7%) | 1/5 |
| B — ảnh treo móc | 1/5 (20,0%) | 4/5 (80,0%) | 3/4 |
| C — 7 ảnh thực tế cũ | 5/10 (50,0%) | 6/10 (60,0%) | 2/5 |

### 7.x.6. Thảo luận

**Nhận diện thuộc tính là điểm mạnh.** Trên ảnh một món, hệ thống nhận đúng loại đồ ở
khoảng 97% trường hợp và màu chính ở khoảng 88%. Mức trang trọng gần như luôn nằm trong
phạm vi ±1 mức so với nhãn chuẩn. Phạm vi này đủ cho bước tư vấn, vì Context Agent đặt mục
tiêu trang trọng theo khoảng (ví dụ [2, 3]) chứ không phải một giá trị đơn lẻ. Các lỗi màu
tập trung ở những màu trầm hoặc pha (xanh olive xám, xanh navy, xanh xám); chất liệu vốn
khó xác định qua ảnh nên chỉ được xem là ước lượng.

**Nhiều lỗi "kiểu đồ" thực chất là lỗi tích hợp.** 8/12 lỗi kiểu đồ xảy ra vì mô hình trả
về tên hợp lý nhưng bộ phân loại của ứng dụng không có tên tương ứng: *camisole, culottes,
leggings, cap, beanie, tunic, sheath dress, evening dress*. Với quần culottes và leggings,
ứng dụng còn không xếp được món đồ vào nhóm "Quần". Đây là lỗi nằm trong phần mềm của đề
tài, không phải giới hạn của mô hình. Sau khi bổ sung các tên này làm từ đồng nghĩa của
kiểu đồ có sẵn (ví dụ *culottes, leggings* → quần tây; *cap, beanie* → mũ), kết quả được
chấm lại từ đúng file kết quả đã lưu, không gọi lại mô hình và không sửa nhãn chuẩn
(Bảng 7.4).

**Bảng 7.4.** Ảnh hưởng của việc bổ sung từ đồng nghĩa vào bộ phân loại (tập A)

| Thuộc tính | Trước | Sau | KTC 95% (sau) |
| :--- | :---: | :---: | :---: |
| Nhóm đồ hiển thị | 54/58 (93,1%) | 56/58 (96,6%) | 88,3–99,0% |
| Kiểu đồ | 46/58 (79,3%) | 53/58 (91,4%) | 81,4–96,3% |

Các lỗi kiểu đồ còn lại là lỗi nhận diện thật: chân váy hoạ tiết bị nhận là quần short, áo
nỉ khoá kéo nửa bị nhận là áo khoác, giày lười đục lỗ bị nhận là giày thể thao; cùng một ảnh
mà mô hình xếp vào nhóm váy liền trong khi nhãn chuẩn là áo, và một ảnh lỗi kết nối. Kết quả
này cho thấy giá trị của việc đánh giá với dịch vụ thật: lỗi tích hợp chỉ lộ ra khi đầu ra
thật của mô hình đi qua toàn bộ hệ thống.

**Tách từng món trong ảnh phức tạp là điểm yếu.** Với ảnh nhiều món trải phẳng, YOLO-World
chỉ giữ được khoảng 30% số món ở chất lượng cắt đạt yêu cầu; có ảnh 9 món nhưng chỉ phát
hiện 1 khung. Ảnh người đang mặc và ảnh treo móc khá hơn: món đồ thường được tìm thấy
(IoU ≥ 0,5 ở 87% và 80% số món), nhưng khung thường hẹp hơn món đồ nên ảnh cắt bị mất gấu
áo, đế giày hoặc tay áo. Ở ảnh một món, YOLO-World không phát hiện được gì trên 11/58 ảnh;
khi đó ứng dụng dùng cả ảnh làm vùng cắt, và độ chính xác thuộc tính trên 11 ảnh này vẫn
tương đương. Như vậy với ảnh một món, cơ chế dự phòng che được lỗi của bộ phát hiện.

**Ý nghĩa với thiết kế hệ thống.** Kết quả cho thấy bước người dùng xác nhận và chỉnh khung
trước khi lưu (mục 4.1, bước 4) là thành phần cần thiết, không chỉ là thủ tục. Bước này cũng
bảo đảm tủ đồ, nguồn dữ liệu duy nhất mà Wardrobe Agent được dùng, chỉ chứa thông tin đã
được người dùng kiểm tra.

**So sánh với bộ phát hiện Gemini chưa thực hiện được.** Ở lượt chạy với bộ phát hiện
Gemini, 54/58 yêu cầu phát hiện vùng bị lỗi (36 lỗi vượt hạn mức HTTP 429 với giới hạn 20
yêu cầu/ngày của gói miễn phí, 7 lỗi HTTP 503, 11 lỗi hết thời gian chờ); toàn bộ 21 yêu
cầu ở tập B và C cũng lỗi. Ứng dụng vẫn hoạt động nhờ chuyển sang cắt cả ảnh, và độ chính
xác thuộc tính chỉ chênh khoảng một ảnh so với lượt YOLO-World. Tuy nhiên đây không phải là
độ chính xác của bộ phát hiện Gemini. Kết quả này cho thấy phụ thuộc vào hạn mức dịch vụ bên
ngoài là một rủi ro vận hành, và là lý do để chọn YOLO-World chạy cục bộ làm bộ phát hiện
mặc định.

### 7.x.7. Hạn chế của đánh giá

- Nhãn thuộc tính (trừ loại đồ) do một người duyệt từ bản nháp; chưa phải nhãn độc lập của
  nhiều người gán.
- Tập B nhỏ (14 ảnh) và gồm ảnh lấy từ Internet, chưa phải ảnh do người dùng thật chụp. Một
  số món nhìn thấy trong ảnh chưa được khoanh, và chưa đo độ chính xác của khung dự đoán
  (khung thừa không bị trừ điểm).
- Mỗi cấu hình chỉ chạy một lần; chất lượng và độ sẵn sàng của dịch vụ bên ngoài thay đổi
  theo thời gian.

### 7.x.8. Hướng cải thiện

1. Đã thực hiện: bổ sung từ đồng nghĩa vào bộ phân loại (Bảng 7.4). Nên tiếp tục ghi nhận
   các tên mới mà mô hình trả về trong quá trình sử dụng.
2. Chạy lại so sánh với bộ phát hiện Gemini khi có hạn mức phù hợp.
3. Nới khung cắt cho ảnh người đang mặc và ảnh treo móc; tìm nguyên nhân YOLO-World bỏ sót
   áo thun đơn lẻ.
4. Mở rộng tập ảnh thực tế do người dùng chụp và có thêm người gán nhãn độc lập.
