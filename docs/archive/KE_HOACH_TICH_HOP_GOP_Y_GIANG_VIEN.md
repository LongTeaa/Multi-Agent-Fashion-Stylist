# KẾ HOẠCH & LỘ TRÌNH TÍCH HỢP CHUYÊN MÔN DỆT MAY - THỜI TRANG
## (Dành cho việc triển khai tuần tự và theo dõi tiến độ dự án)

> **Trạng thái lưu trữ (18/11/2026):** Cả 6 giai đoạn đã hoàn thành và có trong `main` (tính đến lần merge PR #11). Đây là tài liệu lịch sử, không phải nguồn sự thật. Mô hình 5 thuộc tính, 3 tầng đánh giá và trọng số động hiện được định nghĩa tại `../03_domain/FASHION_KNOWLEDGE_BASE.md`; trọng số cụ thể trong tài liệu đó có thể khác với đề xuất ban đầu dưới đây.

> **Mục đích tài liệu:** Tài liệu này vạch ra lộ trình thực hiện từng bước riêng biệt để nâng cấp toàn diện dự án theo bản góp ý chuyên môn của Giảng viên hướng dẫn. Nội dung tài liệu **tập trung hoàn toàn vào lý thuyết nghiệp vụ, sự thay đổi logic giữa hiện trạng và đề xuất mới, cùng các tiêu chí kiểm thử nghiệm thu (Verification) cho từng giai đoạn**

---

## BẢNG TỔNG HỢP TIẾN ĐỘ THỰC HIỆN

| Giai đoạn | Tên nhiệm vụ | Trọng tâm thay đổi | Trạng thái |
| :---: | :--- | :--- | :---: |
| **Giai đoạn 1** | Chuẩn hóa Hồ sơ Dữ liệu Món đồ *(Tầng 1)* | Thêm thang đo Thoải mái (1-5), Phom dáng (1-5) & Độ dài | `[Đã hoàn thành]` |
| **Giai đoạn 2** | Nâng cấp Trợ lý AI Thị giác *(Ingestion)* | Dạy AI tự động nhận diện độ thoáng, phom ôm/rộng qua ảnh | `[Đã hoàn thành]` |
| **Giai đoạn 3** | Nâng cấp Giao diện Kiểm duyệt & Tủ đồ | Cho phép người dùng xem, sửa các chỉ số mới trực quan | `[Đã hoàn thành]` |
| **Giai đoạn 4** | Cải tiến Bộ não Chấm điểm Thẩm mỹ *(Tầng 2)* | Thuật toán Cân bằng Tỷ lệ phom dáng (1-5), độ dài & Ma trận phong cách | `[Đã hoàn thành]` |
| **Giai đoạn 5** | Triển khai Đánh giá Ngữ cảnh & Trọng số động *(Tầng 3)* | Tính điểm Thời tiết, Thoải mái, Chức năng & Đổi bảng trọng số linh hoạt | `[Đã hoàn thành]` |
| **Giai đoạn 6** | Kiểm thử Toàn diện & Hoàn thiện Thuyết minh | Chạy thử nghiệm E2E đối chứng, cập nhật Test Suite và nghiệm thu | `[Đã hoàn thành]` |

---

## NGUYÊN LÝ CỐT LÕI: 2 THỜI ĐIỂM & KIẾN TRÚC 3 TẦNG

Để tránh làm hệ thống quá phức tạp, toàn bộ luồng dữ liệu và nghiệp vụ được phân tách rành mạch theo **2 thời điểm** và **3 tầng xử lý** theo đúng khuyến nghị của Giảng viên:

```
THỜI ĐIỂM 1: KHI UPLOAD ẢNH (Số hóa đồ vào tủ)
==============================================
    [ Ảnh trang phục ]
           │
           ▼ (Gemini Vision phân tích)
    ┌────────────────────────────────────────────────────────────┐
    │ TẦNG 1: GARMENT LEVEL (Lưu trữ tĩnh trong Database)        │
    │ • Formality (1-5) & Occasion                               │
    │ • Comfort (1-5) & Weather Suitability                      │
    │ • Function (functional_flags: outdoor, sun, rain, movement)│
    │ • Silhouette (1-5) & Length (cropped, waist, hip, long)    │
    │ • Màu sắc (Hue/Value/Sat), Chất liệu, Phong cách cơ bản    │
    └────────────────────────────────────────────────────────────┘
           │
           ▼
    Lưu trữ an toàn vào Tủ đồ số (Database)


THỜI ĐIỂM 2: KHI USER CHAT HỎI PHỐI ĐỒ ("Tối nay đi dự tiệc...")
==============================================================
    [ Câu hỏi của User ]
           │
           ▼
    ┌────────────────────────────────────────────────────────────┐
    │ TẦNG 3 (Phần 1): CONTEXT EXTRACTION & TRỌNG SỐ ĐỘNG        │
    │ Context Agent bóc tách hoàn cảnh, thời tiết, nhu cầu:      │
    │ • Kích hoạt Hồ sơ Trọng số phù hợp (Formal, Casual...)     │
    └────────────────────────────────────────────────────────────┘
           │
           ▼ (Wardrobe Agent lọc ứng viên Tầng 1 theo tiêu chí)
    ┌────────────────────────────────────────────────────────────┐
    │ TẦNG 2: OUTFIT LEVEL (Thuộc tính 5: Thẩm mỹ nội tại 0-100) │
    │ Fashion Agent ghép cặp Áo + Quần để tính toán động:        │
    │ • Color Harmony (Bánh xe màu sắc)                          │
    │ • Proportion Balance (Cân đối tỷ lệ phom dáng & độ dài)    │
    │ • Style Compatibility Matrix (Hòa hợp phong cách 0-100)    │
    │ ───► Sinh ra: Outfit Aesthetic Score (Độc lập thời tiết)   │
    └────────────────────────────────────────────────────────────┘
           │
           ▼
    ┌────────────────────────────────────────────────────────────┐
    │ TẦNG 3 (Phần 2): CONTEXT EVALUATION & XẾP HẠNG CUỐI CÙNG   │
    │ Coordinator / Personalization Agent tính các điểm Ngữ cảnh:│
    │ • Weather & Comfort Fit (Trời nóng vs độ mỏng mát/thoải mái│
    │ • Formality Fit (Độ trang trọng yêu cầu vs thực tế)        │
    │ • Functional Fit (Nhu cầu chống nắng, đi xe máy, vận động) │
    │ • Personal Preference Fit (Sở thích cá nhân & lịch sử mặc) │
    │                                                            │
    │ Áp dụng Trọng số Động (Dynamic Weights) theo ngữ cảnh:     │
    │ Final Outfit Score = w_formal·FormalityFit                 │
    │                    + w_comfort·WeatherComfortFit           │
    │                    + w_func·FunctionalFit                  │
    │                    + w_aest·AestheticScore                 │
    │                    + w_pers·PersonalPref                   │
    │ ───► Xuất TOP 3 bộ đồ xuất sắc nhất kèm lời giải thích     │
    └────────────────────────────────────────────────────────────┘
```

---

## CHI TIẾT TỪNG GIAI ĐOẠN TRIỂN KHAI & TIÊU CHÍ NGHIỆM THU

---

### GIAI ĐOẠN 1: CHUẨN HÓA HỒ SƠ DỮ LIỆU MÓN ĐỒ (TẦNG 1 - GARMENT LEVEL)

#### 1. So sánh Hiện trạng vs Đề xuất của Thầy:
* **Hiện trạng:** Hệ thống mới chỉ có thang đo Mức độ trang trọng (1 đến 5), nhãn mùa, nhãn thời tiết và kiểu dáng dưới dạng chữ tự do (như `regular`, `oversized`). Hệ thống hoàn toàn **chưa có thang đo định lượng về Độ thoải mái** và **chưa có thang đo chuẩn cho Phom dáng tổng thể cũng như Độ dài**.
* **Đề xuất của Thầy:** Mỗi món đồ khi số hóa vào tủ đồ phải mang đầy đủ thông số của Tầng 1:
  1. *Độ thoải mái (Thang 1 đến 5):* Đại diện cho cảm giác mặc (độ mềm, co giãn, thoáng khí).
  2. *Dáng tổng thể (Thang 1 đến 5):* Từ 1 (rất ôm sát - Very fitted) đến 3 (vừa vặn - Regular) và 5 (rộng thùng thình - Oversized).
  3. *Độ dài trang phục:* Ngắn lửng ngang eo (Cropped), Ngang hông (Waist/Hip), Dài chạm gót (Long).
  4. *Chức năng & Tiện ích (Thuộc tính 3 của Thầy):* Tận dụng trường `functional_flags: list[str]` đã có sẵn trong codebase để chuẩn hóa theo bộ từ điển nhãn của Thầy (`movement`, `outdoor`, `rain`, `sun`, `work`, `sport`, `protection`), phục vụ các ngữ cảnh vận động hoặc đi xe máy ngoài trời.

#### 2. Cần thực hiện:
* Cập nhật cấu trúc lưu trữ của Tủ đồ số để bổ sung thêm 3 thuộc tính định lượng trên (`comfort_level`, `silhouette_level`, `length`).
* Chuẩn hóa từ điển danh mục (Taxonomy) cho `functional_flags` hiện có để nhận diện đúng các tag chức năng của Thầy.
* Thiết lập quy tắc chuyển tiếp an toàn (Backward Compatibility): Với toàn bộ trang phục cũ đã có sẵn trong tủ, hệ thống tự động gán giá trị mặc định chuẩn mực (Độ thoải mái mức 3 - Trung bình; Phom dáng mức 3 - Vừa vặn; Độ dài tiêu chuẩn) để đảm bảo không xảy ra xung đột dữ liệu hay làm mất đồ của người dùng.
* Bổ sung quy tắc kiểm tra tính hợp lệ: Nghiêm cấm lưu các giá trị nằm ngoài thang đo từ 1 đến 5.

#### 3. Tiêu chí nghiệm thu (Verification Checklist):
- [x] Cấu trúc dữ liệu tủ đồ mới chấp nhận đầy đủ 3 trường thông tin: Độ thoải mái (1-5), Dáng tổng thể (1-5), và Độ dài.
- [x] Bộ từ điển thẻ chức năng (`functional_flags`) được định nghĩa chuẩn hóa và sẵn sàng tiếp nhận các tag của Thầy.
- [x] Dữ liệu 16 món đồ hiện tại trong tủ đồ vẫn nguyên vẹn 100%, tự động mang giá trị tiêu chuẩn và không bị lỗi.
- [x] Hệ thống tự động từ chối hoặc báo lỗi nếu có dữ liệu vi phạm thang đo (ví dụ mức thoải mái bằng 0 hoặc lớn hơn 5).

---

### GIAI ĐOẠN 2: NÂNG CẤP TRỢ LÝ AI THỊ GIÁC & QUY TRÌNH SỐ HÓA (INGESTION)

#### 1. So sánh Hiện trạng vs Đề xuất của Thầy:
* **Hiện trạng:** Trợ lý AI Thị giác (Gemini Vision) khi phân tích ảnh quần áo chỉ bóc tách: loại áo/quần, màu sắc, chất vải, họa tiết và mức trang trọng. Khi gặp thuộc tính độ thoải mái hay phom dáng, AI chưa được hướng dẫn để phân tích.
* **Đề xuất của Thầy:** Người dùng không cần phải tự tay điền các thông số kỹ thuật này. Hệ thống thông minh phải tự nhìn ảnh cấu trúc may mặc và chất liệu vải để tự động suy luận ra độ thoải mái và phom dáng.

#### 2. Cần thực hiện:
* Nâng cấp hướng dẫn nghiệp vụ thời trang cho Trợ lý AI Thị giác:
  * *Về độ thoải mái:* Hướng dẫn AI nhìn bề mặt chất liệu (ví dụ vải thun cotton mềm, len dệt kim co giãn $\rightarrow$ gợi ý mức thoải mái cao 4–5; vải thô cứng, giả da bí $\rightarrow$ gợi ý mức 1–2).
  * *Về phom dáng:* Hướng dẫn AI nhìn độ rủ và đường cắt may của trang phục (dáng bó sát đường cong $\rightarrow$ mức 1–2; dáng suông thẳng $\rightarrow$ mức 3; dáng thụng vai rơi rộng rãi $\rightarrow$ mức 4–5).
  * *Về độ dài:* Hướng dẫn AI ước lượng tỷ lệ chiều dài thân áo hoặc ống quần (ngắn lửng, ngang hông, hay dài).
* Đảm bảo luồng trích xuất dữ liệu trả về đầy đủ các thông số định lượng này kèm mức độ tin cậy để đưa sang bước kiểm duyệt.

#### 3. Tiêu chí nghiệm thu (Verification Checklist):
- [x] Khi tải lên ảnh áo thun cotton phom rộng, AI tự động gợi ý mức thoải mái $\ge 4$ và dáng rộng $\ge 4$.
- [x] Khi tải lên ảnh áo sơ mi âu phục ôm sát, AI tự động gợi ý mức trang trọng cao và dáng ôm sát (mức 1-2).
- [x] Quy trình số hóa truyền tải thông suốt các giá trị này từ khâu phân tích ảnh sang giao diện người dùng mà không bị rơi rụng thông tin.

---

### GIAI ĐOẠN 3: NÂNG CẤP GIAO DIỆN KIỂM DUYỆT & TỦ ĐỒ CÁ NHÂN (UI/UX)

#### 1. So sánh Hiện trạng vs Đề xuất của Thầy:
* **Hiện trạng:** Màn hình kiểm duyệt trang phục sau khi tải ảnh lên chỉ hiển thị các trường: Danh mục, Màu, Họa tiết, Chất liệu, Phong cách, Độ trang trọng. Người dùng chưa thể nhìn thấy hoặc điều chỉnh độ thoải mái và phom dáng.
* **Đề xuất của Thầy:** Trải nghiệm người dùng phải minh bạch. Người dùng nhìn thấy những gì AI gợi ý, nhưng có toàn quyền bấm chỉnh lại theo cảm nhận thực tế của mình trước khi chính thức bấm lưu vào tủ đồ.

#### 2. Cần thực hiện:
* Bổ sung vào Màn hình Kiểm duyệt món đồ:
  * Thước đo / Thanh chọn mức độ thoải mái trực quan từ 1 đến 5 sao.
  * Hộp chọn phom dáng tổng thể với các nhãn tiếng Việt dễ hiểu: *Rất ôm sát (1) — Ôm vừa (2) — Tiêu chuẩn (3) — Thoải mái/Rộng (4) — Rộng thùng thình (5)*.
  * Hộp chọn độ dài: *Dáng ngắn lửng — Dài ngang hông — Dáng dài*.
* Bổ sung hiển thị trên Thẻ món đồ trong Tủ đồ cá nhân: Thêm huy hiệu (badge) nhỏ thể hiện mức độ thoải mái và dáng áo để người dùng dễ dàng quản lý tủ đồ số của mình.

#### 3. Tiêu chí nghiệm thu (Verification Checklist):
- [x] Màn hình kiểm duyệt hiển thị rõ ràng các trường thông tin mới với bố cục thoáng đãng, dễ tương tác trên cả điện thoại và máy tính.
- [x] Người dùng có thể thay đổi các giá trị độ thoải mái và phom dáng bằng thao tác bấm chọn đơn giản.
- [x] Khi bấm "Xác nhận lưu vào tủ đồ", các thông số người dùng đã chọn được lưu chính xác vào tủ đồ số.

---

### GIAI ĐOẠN 4: CẢI TIẾN BỘ NÃO CHẤM ĐIỂM THẨM MỸ NỘI TẠI & TỶ LỆ (TẦNG 2 - OUTFIT LEVEL)

> **Bản chất nghiệp vụ:** Đây chính là **Thuộc tính số 5 (Aesthetic Compatibility — Thang điểm 0 đến 100)** trong Khung 5 thuộc tính của Thầy. Thuộc tính này **không lưu trữ tĩnh** trên từng món đồ khi upload ảnh, mà được Trợ lý Phối đồ (Fashion Agent) tính toán động ở Tầng 2 khi ghép các món đồ lại với nhau thành một bộ trang phục (Outfit) hoàn chỉnh. Nó đại diện cho vẻ đẹp và sự cân đối **nội tại** của bộ đồ, **hoàn toàn độc lập với điều kiện thời tiết hay hoàn cảnh bên ngoài**.

#### 1. So sánh Hiện trạng vs Đề xuất của Thầy:
* **Hiện trạng:** Hệ thống đã chấm điểm phối màu rất tốt (theo bánh xe màu sắc) và độ hòa hợp phong cách. Tuy nhiên, quy tắc kiểm tra **tỷ lệ phom dáng** còn rất thô sơ (chỉ so sánh text tự do), chưa tận dụng được thang đo định lượng 1–5 giữa dáng áo và dáng quần.
* **Đề xuất của Thầy:** Thẩm mỹ thời trang phải đánh giá được tính cân đối về mặt tỷ lệ (Proportion): Tránh trường hợp "trên thùng thình lùng bùng - dưới cũng thụng rộng quét đất" khiến nuốt chửng dáng vóc; hoặc "trên bó nghẽn - dưới cũng bó sát". Khen ngợi các tỷ lệ phối kinh điển (Áo ôm + Quần suông rộng, hoặc Áo rộng + Quần vừa vặn, Áo lửng cropped + Quần cạp cao).

#### 2. Cần thực hiện:
* **Nâng cấp Thuật toán Cân đối Tỷ lệ Phom dáng & Độ dài (Proportion Balance):**
  * So sánh chỉ số `silhouette_level` (1-5) và `length` của phần thân trên (áo) và phần thân dưới (quần/chân váy).
  * *Quy tắc thưởng (Tương phản hài hòa):* 
    * Áo dáng ôm (mức 1–2) + Quần suông/ống rộng (mức 3–5) $\rightarrow$ Thưởng điểm tối đa.
    * Áo dáng rộng (mức 4–5) + Quần dáng vừa vặn/ôm (mức 2–3) $\rightarrow$ Thưởng điểm cao.
    * Áo lửng ngang eo (Cropped) + Quần dài cạp cao (Long/High-waist) $\rightarrow$ Thưởng tỷ lệ kéo dài chân.
  * *Quy tắc phạt (Cực đoan mất cân đối):* 
    * Áo siêu rộng (mức 5) + Quần siêu thụng (mức 5) $\rightarrow$ Phạt điểm (trừ trường hợp phong cách là Streetwear).
    * Áo bó sát (mức 1) + Quần siêu bó (mức 1) $\rightarrow$ Phạt điểm (trừ trang phục thể thao/activewear).
* **Chuẩn hóa Ma trận Tương thích Phong cách (Style Compatibility Matrix):**
  * Đối chiếu bảng ma trận phong cách hiện tại với các ví dụ thực tế của Thầy:
    * `casual × casual = High (0.95–1.0)`
    * `smart casual × smart casual = High (0.95–1.0)`
    * `smart casual × formal = High/Medium (0.85)`
    * `casual × formal = Medium/Low (0.55)`
    * `formal × streetwear = Low (0.20)`
    * Áo thun casual + Quần jeans = High; Áo thun casual + Quần âu formal = Medium; Hoodie oversized + Blazer formal = Low/Medium; Giày thể thao + Đầm dạ hội = Low.
  * Đảm bảo thang điểm trả về liên tục từ 0 đến 100 (tương đương 0.0 đến 1.0).
* **Công thức Điểm Thẩm mỹ Tầng 2 (Outfit Aesthetic Score):**
  $$\text{AestheticScore} = 0.40 \cdot \text{ColorHarmony} + 0.35 \cdot \text{ProportionBalance} + 0.25 \cdot \text{StyleCompatibility}$$

#### 3. Tiêu chí nghiệm thu (Verification Checklist):
- [x] Thuật toán nhận diện chính xác và phạt điểm các bộ phối có tỷ lệ mất cân đối (trên dưới cùng siêu thùng thình hoặc cùng siêu bó sát).
- [x] Các bộ phối kinh điển (áo ôm + quần suông; áo rộng + quần vừa) đạt điểm tỷ lệ thẩm mỹ cao nhất.
- [x] Tỷ lệ độ dài (áo cropped + quần cạp cao) được nhận diện và tính điểm thưởng tỷ lệ.
- [x] Ma trận tương thích phong cách bao phủ đầy đủ các cặp phối của Thầy và trả về điểm số liên tục (0–100) thay vì Yes/No.
- [x] Điểm thẩm mỹ Tầng 2 phản ánh độc lập vẻ đẹp nội tại của bộ đồ, không bị trừ điểm oan khi thời tiết ngoài trời thay đổi.

---

### GIAI ĐOẠN 5: ĐÁNH GIÁ SỰ PHÙ HỢP NGỮ CẢNH & CƠ CHẾ TRỌNG SỐ ĐỘNG (TẦNG 3 - CONTEXT LEVEL)

#### 1. So sánh Hiện trạng vs Đề xuất của Thầy:
* **Hiện trạng:** Hệ thống đang sử dụng một công thức cố định với tỷ lệ phần trăm bất di bất dịch cho mọi hoàn cảnh: `30% Màu + 20% Phong cách + 20% Trang trọng + 20% Thời tiết + 10% Tỷ lệ`.
* **Đề xuất của Thầy:** Hệ thống **không được có một công thức duy nhất**, mà trọng số phải thay đổi linh hoạt theo hoàn cảnh:
  * Đi hội nghị / Phỏng vấn $\rightarrow$ Ưu tiên Trang trọng (30%) & Thẩm mỹ (25%) lên hàng đầu (Thoải mái chỉ chiếm 15%).
  * Đi chơi dạo phố / Du lịch ngày nóng $\rightarrow$ Ưu tiên Thoải mái (30%) & Thời tiết (25%) lên hàng đầu (Trang trọng chỉ chiếm 10%).
  * Đi vận động / Hoạt động ngoài trời $\rightarrow$ Ưu tiên Chức năng bảo vệ & Tiện lợi vận động.

#### 2. Cần thực hiện:
* **Bước 1: Thuật toán Tính toán các Chỉ số Phù hợp Ngữ cảnh (Context Fit Scores):**
  1. *Weather & Comfort Fit:* So khớp nhiệt độ/thời tiết thực tế với `comfort_level` và `weather_suitability` của món đồ.
     * Trời nóng oi bức: Bộ đồ vải mềm mát, `comfort_level` cao ($\ge 4$) được điểm tối đa; đồ dày bí bó chật ($\le 2$) bị điểm thấp.
     * Trời lạnh giá: Bộ đồ giữ ấm, có áo khoác phù hợp được điểm tối đa.
  2. *Formality Fit:* So khớp độ trang trọng yêu cầu của sự kiện (`target_formality_range`) với mức trang trọng trung bình của các món đồ (`formality_level`).
  3. *Functional Fit:* So khớp yêu cầu thực tế với các nhãn trong `functional_flags` (ví dụ: người dùng đi xe máy $\rightarrow$ ưu tiên `movement`, `outdoor`, `sun`, `protection`).
  4. *Personal Preference Fit:* So khớp với hồ sơ sở thích cá nhân và tránh lặp lại đồ vừa mặc trong 48h–72h.
* **Bước 2: Xây dựng Bộ Hồ sơ Trọng số Linh hoạt (Context Weight Profiles):**
  1. *Hồ sơ Trang trọng (Formal Profile - Hội nghị, tiệc cưới, phỏng vấn):*
     * Formality: 30% | Aesthetic: 25% | Context: 20% | Comfort: 15% | Personal: 10%
  2. *Hồ sơ Đời thường / Thoải mái (Casual/Comfort Profile - Cà phê, dạo phố, du lịch ngày nóng):*
     * Comfort: 30% | Weather: 25% | Function: 20% | Aesthetic: 15% | Formality: 10%
  3. *Hồ sơ Vận động / Ngoài trời (Active Profile - Thể thao, đi xe máy, di chuyển nhiều):*
     * Function: 30% | Comfort: 25% | Weather: 20% | Aesthetic: 15% | Formality: 10%
  4. *Hồ sơ Cân bằng (Balanced Profile - Hỏi chung chung không rõ tiêu chí):*
     * Phân bổ cân bằng mặc định.
* **Bước 3: Dạy Context Agent nhận diện ý định & Áp dụng Trọng số Động (Coordinator Agent):**
  * Context Agent phân tích ngôn ngữ tự nhiên (ví dụ: *"ưu tiên thoải mái"*, *"mặc mát mẻ"*, *"cần trang trọng"*, *"đi xe máy ngoài trời"*) để kích hoạt đúng Hồ sơ Trọng số.
  * Coordinator Agent tổng hợp điểm xếp hạng cuối cùng:
    $$\text{Final Outfit Score} = w_{\text{formality}} \cdot \text{FormalityFit} + w_{\text{comfort}} \cdot \text{WeatherComfortFit} + w_{\text{func}} \cdot \text{FunctionalFit} + w_{\text{aest}} \cdot \text{AestheticScore} + w_{\text{pers}} \cdot \text{PersonalPref}$$
  * Nâng cấp lời giải thích của Stylist (`explanation_vi`): Giải thích mạch lạc cho người dùng biết vì sao bộ đồ được chọn dựa trên chính yếu tố được ưu tiên cao nhất trong hoàn cảnh đó.

#### 3. Tiêu chí nghiệm thu (Verification Checklist):
- [x] Khi giả lập thời tiết nóng, bộ trang phục gồm áo thun mềm + quần mát đạt điểm Weather & Comfort Fit vượt trội so với bộ đồ vải dày cứng.
- [x] Thử nghiệm với cùng một tủ đồ cá nhân:
  * Khi yêu cầu *"Tối nay đi dự tiệc cưới trang trọng"*: Hệ thống tự động chọn Hồ sơ Trang trọng, đưa bộ âu phục/váy dạ hội lên vị trí số 1.
  * Khi yêu cầu *"Hôm nay trời nóng quá, đi cà phê bạn bè ưu tiên thoải mái"*: Hệ thống tự động chuyển sang Hồ sơ Thoải mái, đưa bộ áo thun quần lửng thoáng mát lên vị trí số 1 (dù bộ âu phục có điểm thẩm mỹ cao hơn).
  * Khi yêu cầu *"Tôi đi xe máy ngoài trời nắng"*: Hệ thống ưu tiên chọn đồ có gắn nhãn `outdoor`, `sun`, `movement`.
- [x] Điểm số tổng kết và thứ tự xếp hạng thay đổi rõ rệt và hợp lý giữa các hoàn cảnh khác nhau.
- [x] Lời giải thích của Stylist nêu bật đúng lý do cốt lõi theo trọng số ưu tiên của hoàn cảnh.

---

### GIAI ĐOẠN 6: NGHIỆM THU TOÀN DIỆN, TEST HỒI QUY & HOÀN THIỆN THUYẾT MINH

#### 1. Mục tiêu:
Đảm bảo toàn bộ hệ thống vận hành trơn tru từ đầu đến cuối, test suite pass 100% không phát sinh lỗi hồi quy và chuẩn bị đầy đủ luận cứ khoa học để nhóm bảo vệ đồ án tốt nghiệp xuất sắc trước Hội đồng.

#### 2. Cần thực hiện:
* **Kiểm thử xuyên suốt toàn hệ thống (End-to-End Test):** Đi từ khâu nạp đồ mới $\rightarrow$ AI tự điền độ thoải mái $\rightarrow$ Người dùng lưu đồ $\rightarrow$ Vào khung chat hỏi phối đồ $\rightarrow$ Kiểm tra các bộ đồ gợi ý và lời giải thích của Stylist xem có mạch lạc, đúng chuyên môn không.
* **Cập nhật Bộ Kiểm thử Tự động (Regression & Unit Tests):** Cập nhật lại các test case cũ trong `backend/tests/unit/` (đặc biệt là `test_fashion_scoring.py` và `test_personalization.py`) để đồng bộ với công thức 3 tầng và các thuộc tính mới, đảm bảo 100% tests pass xanh.
* **Hoàn thiện tài liệu Domain Knowledge Base:** Đưa toàn bộ mô hình 5 thuộc tính, 3 tầng đánh giá và cơ chế trọng số động vào tài liệu kỹ thuật của dự án.
* **Chuẩn bị kịch bản Demo:** Chuẩn bị sẵn 2 kịch bản tương phản rõ rệt (Hội nghị vs Đi chơi) để trình chiếu cho các thầy cô trong buổi bảo vệ.

#### 3. Tiêu chí nghiệm thu (Verification Checklist):
- [x] Hệ thống không phát sinh bất kỳ lỗi kỹ thuật nào trong toàn bộ luồng trải nghiệm.
- [x] Toàn bộ bộ Unit Test và Integration Test hiện có chạy pass 100% không có lỗi hồi quy.
- [x] Lời giải thích của Stylist thể hiện rõ tư duy chuyên môn: nêu rõ lý do về sự hài hòa màu sắc, độ cân bằng phom dáng và sự phù hợp với thời tiết.
- [x] Tài liệu thuyết minh đồ án hoàn chỉnh, giải thích rõ cơ sở khoa học của việc định lượng thời trang thành các chỉ số mức độ từ 1 đến 5 và cơ chế trọng số động.

---

## NGUYÊN TẮC THỰC HIỆN TUẦN TỰ
* Nhóm sẽ tiến hành **lần lượt từ Giai đoạn 1 đến Giai đoạn 6**.
* Mỗi khi hoàn thành một giai đoạn, chúng ta sẽ đối chiếu lại với **Tiêu chí nghiệm thu (Verification Checklist)** của giai đoạn đó. Khi toàn bộ các ô kiểm tử đều đạt yêu cầu, chúng ta mới chuyển sang giai đoạn tiếp theo.
