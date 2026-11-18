# Fashion Domain Knowledge Base & 3-Tier Scoring Engine Architecture

## 1. Mục đích & Cơ sở Khoa học (Purpose & Theoretical Foundation)

Tài liệu này chuẩn hóa toàn bộ tri thức chuyên môn ngành Dệt may - Thời trang tích hợp vào hệ sinh thái Multi-Agent Fashion Stylist.
Nhằm khắc phục triệt để các hạn chế của các hệ thống khuyến nghị thời trang truyền thống (chỉ dùng một công thức cố định hoặc phụ thuộc hoàn toàn vào black-box LLM), hệ thống áp dụng:
1. **Mô hình 5 Thuộc tính Trang phục Định lượng** (5-Dimensional Garment Profile).
2. **Kiến trúc Đánh giá Phân tầng 3 Tầng** (3-Tier Evaluation Architecture), tách biệt hoàn toàn vẻ đẹp thẩm mỹ nội tại của trang phục với sự phù hợp hoàn cảnh bên ngoài.
3. **Cơ chế Trọng số Động theo Ngữ cảnh** (Dynamic Context Weight Profiles).

---

## 2. Mô hình 5 Thuộc tính Trang phục Định lượng (5-Dimensional Garment Profile)

Mỗi món đồ trong tủ đồ số hóa (`WardrobeItem`) được chuẩn hóa và lượng hóa theo 5 chiều kích chuyên môn:

### 2.1 Mức độ Trang trọng (`formality_level`: 1 .. 5)
* **Mức 1 (Very Casual / At-home):** Đồ mặc nhà, đồ ngủ, áo ba lỗ, dép lê.
* **Mức 2 (Casual):** Áo thun cổ tròn, quần jeans rách, giày sneaker vải canvas, quần soóc dạo phố.
* **Mức 3 (Smart Casual):** Áo polo, sơ mi ngắn tay, quần kaki/chino, chân váy midi, giày lười loafer.
* **Mức 4 (Business Casual / Semi-formal):** Áo sơ mi dài tay cài nút, quần tây âu, áo blazer mỏng, giày tây/oxford hoặc cao gót cổ điển.
* **Mức 5 (Formal / Black Tie):** Bộ Comple/Suit cao cấp, tuxedo, đầm dạ hội dài, cà vạt, nơ cổ.

### 2.2 Mức độ Thoải mái & Mềm mát (`comfort_level`: 1 .. 5)
* **Mức 1 (Very Restrictive):** Đồ bó sát định hình, chất vải dày cứng không co giãn, giữ nhiệt cao (heavy wool, da cứng, áo nịt corset).
* **Mức 2 (Structured / Low Comfort):** Đồ may đo đứng form công sở, ít co giãn (áo vest dựng form, quần tây phẳng nếp, giày da đế cứng).
* **Mức 3 (Standard):** Trang phục hàng ngày có độ co giãn nhẹ hoặc phom dáng vừa vặn tiêu chuẩn (cotton thường, denim co giãn).
* **Mức 4 (Comfortable & Breathable):** Vải mềm, thông thoáng khí tốt (linen, đũi, modal, cotton xước mỏng).
* **Mức 5 (Maximum Comfort / Flowing):** Vải lụa mỏng, cotton hữu cơ siêu mềm, phom dáng bay bổng, thoáng mát tuyệt đối, không gò bó.

### 2.3 Phom dáng & Độ rộng (`silhouette_level`: 1 .. 5)
* **Mức 1 (Skinny / Tight):** Ôm sát cơ thể (áo croptop bó, quần skinny, legging).
* **Mức 2 (Slim Fit):** Ôm vừa vặn theo đường nét cơ thể.
* **Mức 3 (Regular / Straight Fit):** Phom suông vừa vặn tiêu chuẩn, thẳng hàng từ hông/vai xuống.
* **Mức 4 (Loose / Relaxed Fit):** Phom rộng thoải mái, phóng khoáng.
* **Mức 5 (Oversized / Baggy):** Phom cực rộng, thùng thình, thụng sâu (phong cách hip-hop, streetwear oversized).

Giá trị đã lưu là nguồn sự thật: mức `3` do người dùng xác nhận được dùng nguyên vẹn, không bị suy đoán lại từ chữ trong `fit`/tên món. Suy luận từ từ khóa (`oversized`/`baggy` → 5, `relaxed`/`loose`/`wide` → 4, `slim`/`fitted` → 2, `skinny`/`tight` → 1) chỉ áp dụng khi dữ liệu thật sự thiếu, và một lần cho dữ liệu cũ qua migration `0014`.

### 2.4 Chiều dài Trang phục (`length`)
The canonical MVP taxonomy is shared by every garment category: `cropped`, `waist`, `hip`, and `long`. More granular category-specific lengths are outside the MVP and MUST be normalized to one of these four values before persistence.

Ý nghĩa độ dài phụ thuộc danh mục:

| Danh mục | Giá trị có ý nghĩa tỷ lệ | Mặc định khi thiếu |
| :--- | :--- | :--- |
| `top`, `outerwear` | `cropped`, `waist`, `hip`, `long` (điểm kết thúc trên thân) | `cropped` cho crop top/bolero, `long` cho trench/măng tô, còn lại `hip` |
| `bottom`, `dress` | chỉ `cropped` (ngắn: short, mini, capri) và `long` (dài) | suy ra từ loại đồ; `waist`/`hip` được coi là chưa xác định |
| `footwear`, `accessory` | không dùng cho tỷ lệ | `hip` (bỏ qua khi chấm điểm) |

### 2.5 Nhãn Chức năng Thực tế (`functional_flags`)
Danh sách nhãn đa trị phục vụ thích ứng hoàn cảnh vận động thực tế:
* `sun`: Khả năng chống nắng (UPF, dài tay che phủ).
* `movement`: Phù hợp vận động, co giãn thoải mái, dễ bước lên xe máy/phương tiện.
* `outdoor`: Chống bám bụi, bền bỉ ngoài trời.
* `rain`: Phù hợp ngữ cảnh mưa.
* `water_resistant`: Chống nước nhẹ, đi mưa nhỏ.
* `work`: Đạt quy chuẩn tác phong văn phòng, công sở.
* `sport`: Phù hợp hoạt động thể thao.
* `protection`: Có đặc tính bảo vệ hoặc che phủ.
* `light`: Vải hoặc kết cấu nhẹ.
* `heavy`: Vải hoặc kết cấu dày, nặng.

Các nhãn đồng nghĩa phổ biến được ánh xạ về từ điển chuẩn trước khi lưu (ví dụ `waterproof` → `water_resistant`, `breathable` → `light`, `stretch` → `movement`, `uv` → `sun`). Nhãn không nhận diện được bị từ chối khi chỉnh sửa; với dữ liệu cũ, migration `0014` chuyển chúng sang `free_text_tags` để không mất thông tin.

---

## 3. Kiến trúc Đánh giá Phân tầng 3 Tầng (3-Tier Evaluation Architecture)

```mermaid
graph TD
    A["Tủ đồ Người dùng (Wardrobe Inventory)"] --> Tier1["TẦNG 1: BỘ LỌC CỨNG (Item & Invariant Level)"]
    Tier1 -->|"Loại bỏ đồ không hợp lệ, phân loại slot role"| ValidOutfits["Tập hợp các bộ đồ hoàn chỉnh (Valid Combos)"]

    ValidOutfits --> Tier2["TẦNG 2: ĐIỂM THẨM MỸ NỘI TẠI (Aesthetic Score)
    - Hài hòa Màu sắc: 40%
    - Cân bằng Tỷ lệ Phom dáng: 35%
    - Tương thích Phong cách: 25%"]

    Tier2 --> Tier3["TẦNG 3: SỰ PHÙ HỢP NGỮ CẢNH & TRỌNG SỐ ĐỘNG (Context Fit & Dynamic Weights)
    - Nhận diện ý định & kích hoạt Hồ sơ Trọng số:
      * Formal Profile (Trang trọng 30%, Thẩm mỹ 25%, Thoải mái 15%)
      * Comfort Profile (Thời tiết/Thoải mái 55%, Chức năng 20%, Thẩm mỹ 15%)
      * Active Profile (Chức năng 30%, Thời tiết/Thoải mái 45%, Thẩm mỹ 15%)"]

    Tier3 --> FinalRanking["Xếp hạng Top 1, Top 2, Top 3 & Lời giải thích chuyên môn (VI)"]
```

### 3.1 Tầng 1: Bộ Lọc Cứng (Item & Invariant Level)
* Đảm bảo tính toàn vẹn thời trang tối thiểu:
  * Branch A: `TOP + BOTTOM + FOOTWEAR` (+ `OUTERWEAR` / `ACCESSORY` tùy chọn).
  * Branch B: `DRESS + FOOTWEAR` (+ `OUTERWEAR` / `ACCESSORY` tùy chọn).
* Loại bỏ các món đồ đang giặt/không khả dụng (`is_active = False`).
* Giới hạn không gian tổ hợp: Tối đa 15 món đồ mỗi nhóm danh mục để kiểm soát ngân sách hiệu năng p95 < 5 giây.

### 3.2 Tầng 2: Điểm Thẩm mỹ Nội tại (Outfit Aesthetic Score)

Canonical stored styles `athletic`, `street`, and `business` map to the matrix's `sporty`, `streetwear`, and `formal` respectively. This normalization MUST apply before pair/clash checks.
Điểm thẩm mỹ phản ánh vẻ đẹp tự thân và tính hòa hợp thị giác của bộ trang phục, **hoàn toàn độc lập với thời tiết ngoài trời**:

$$\text{AestheticScore} = 0.40 \cdot \text{ColorHarmony} + 0.35 \cdot \text{ProportionBalance} + 0.25 \cdot \text{StyleCompatibility}$$

1. **Hài hòa Màu sắc (`ColorHarmony` - 40%):**
   * Tất cả màu trung tính (Neutral palette): `1.00`.
   * Nền trung tính + 1 điểm nhấn màu sắc: `0.95`.
   * Phối đơn sắc (Monochromatic): `0.90`.
   * Phối màu tương đồng (Analogous): `0.85`.
   * Phối màu tương phản bổ sung có neo trung tính: `0.80`.
   * Quá 3 họ màu bão hòa không có neo trung tính: Phạt điểm nặng (`0.20`).
2. **Cân bằng Tỷ lệ Phom dáng (`ProportionBalance` - 35%):** điểm phân cấp, không phải đạt/không đạt, để các tỷ lệ kinh điển thực sự xếp trên các bộ chỉ "không lỗi".
   * *Ma trận phom áo × phom quần (điểm nền):*

     | Áo \ Quần | 1 | 2 | 3 | 4 | 5 |
     | :---: | :---: | :---: | :---: | :---: | :---: |
     | **1** | 0.60 | 0.78 | 0.95 | 0.95 | 0.95 |
     | **2** | 0.78 | 0.82 | 0.95 | 0.95 | 0.95 |
     | **3** | 0.82 | 0.86 | 0.85 | 0.88 | 0.84 |
     | **4** | 0.92 | 0.92 | 0.92 | 0.74 | 0.66 |
     | **5** | 0.90 | 0.92 | 0.92 | 0.66 | 0.55 |

     * Tỷ lệ vàng — áo ôm (1..2) + quần suông/rộng (3..5): `0.95`.
     * Đối trọng kinh điển — áo rộng (4..5) + quần vừa/ôm (2..3): `0.92`.
     * Tiêu chuẩn — suông + suông (3 + 3): `0.85`.
     * Mất cân đối — cùng rộng giảm dần `0.74` (4+4) → `0.66` (4+5) → `0.55` (5+5); cùng bó `0.78` (1+2) → `0.60` (1+1).
     * Ngoại lệ: yêu cầu phong cách Streetwear chấm mọi cặp rộng + rộng (≥ 4) là `0.92`; thể thao/activewear chấm 1 + 1 là `0.92`.
   * *Điều chỉnh theo độ dài:* áo `cropped`/`waist` + quần dài: `+0.05` (kéo dài chân, đưa tỷ lệ vàng lên `1.0`); áo `long` + quần ngắn: `-0.10`.
   * *Lớp ngoài:* áo khoác ngắn hoặc dài phủ trên quần/đầm dài `+0.03`; áo khoác dài trên quần/đầm ngắn `-0.10`; bẫy ba lớp cồng kềnh (khoác 5 + áo ≥ 4 + quần 5) `-0.15` trừ Streetwear.
   * *Đầm:* điểm nền `0.92`, áp dụng cùng quy tắc lớp ngoài; đầm 5 dưới khoác 5 `-0.10` trừ Streetwear.
   * *Họa tiết:* `-0.30` cho mỗi món chính có họa tiết sau món đầu tiên; thêm `-0.20` khi cả áo và quần cùng có họa tiết.
3. **Tương thích Phong cách (`StyleCompatibility` - 25%):**
   * Thang điểm ma trận đối xứng liên tục:
     * `casual × casual = 1.0`
     * `smart_casual × formal = 0.85`
     * `casual × formal = 0.55`
     * `formal × streetwear = 0.20`

### 3.3 Tầng 3: Sự Phù hợp Ngữ cảnh & Cơ chế Trọng số Động (Context Fit & Dynamic Weights)

Fashion shortlisting MUST use these context weights (neutral personal score `0.5`) before the 50-candidate cutoff. It MUST NOT shortlist solely by aesthetic score. Personalization then applies actual preferences to those candidates. Optional layers failing the requested weather MUST not be added through automatic retrieval relaxation unless explicitly required.

Functional fit uses recorded `functional_flags`. A name such as sneakers, jacket, or waterproof coat alone is not evidence of a capability. Recorded `water_resistant` also satisfies `rain`; `rain` alone MUST NOT imply water resistance. These are bounded product heuristics, not guarantees of fabric performance or universal aesthetic judgments.
Điểm tổng kết cuối cùng là tích vô hướng giữa Vector Hồ sơ Trọng số và Vector Điểm Phù hợp Ngữ cảnh:

$$\text{FinalScore} = w_{\text{formality}} \cdot \text{FormalityFit} + w_{\text{comfort}} \cdot \text{WeatherComfortFit} + w_{\text{func}} \cdot \text{FunctionalFit} + w_{\text{aest}} \cdot \text{AestheticScore} + w_{\text{pers}} \cdot \text{PersonalPref} - \text{BehaviorPenalty}$$

`PersonalPref` chỉ đo mức hợp gu (phong cách, bảng màu, ưu tiên, điểm học từ đánh giá sao). `BehaviorPenalty` là hình phạt hành vi: phạt lặp đồ (bộ y hệt đã mặc trong 72 giờ `-0.40`; mỗi món chính đã mặc trong 48 giờ `-0.15`, tối đa `-0.30`) và phạt vi phạm "tránh" khi buộc phải nới lỏng (`-0.10` mỗi vi phạm). Hình phạt nằm **ngoài** trọng số nên vẫn có hiệu lực với hồ sơ đặt $w_{\text{pers}} = 0$ (Comfort, Active). Kết quả được kẹp trong `[0, 1]`.

| Hồ sơ Trọng số (Profile) | Hoàn cảnh kích hoạt tiêu biểu | $w_{\text{formality}}$ | $w_{\text{comfort}}$ | $w_{\text{func}}$ | $w_{\text{aest}}$ | $w_{\text{pers}}$ |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Formal Profile** | Hội nghị, tiệc cưới, phỏng vấn, lễ kỷ niệm | **0.30** | 0.15 | 0.20 | **0.25** | 0.10 |
| **Comfort Profile** | Cà phê dạo phố, du lịch, ngày nắng nóng oi bức | 0.10 | **0.55** | 0.20 | 0.15 | 0.00 |
| **Active Profile** | Chơi thể thao, đi xe máy, di chuyển ngoài trời | 0.10 | **0.45** | **0.30** | 0.15 | 0.00 |
| **Balanced Profile** | Yêu cầu chung chung không nêu rõ ưu tiên | 0.20 | 0.20 | 0.20 | 0.20 | 0.20 |

`WeatherComfortFit` is one combined score, so the comfort and weather shares from the advisor examples are aggregated into a single normalized weight. Every profile MUST sum to `1.00`.

---

## 4. Kịch bản Thực nghiệm Đối chứng Tương phản (Contrastive Demonstration Scenarios)

Được tự động kiểm chứng và bảo chứng bởi bộ test tích hợp `backend/tests/integration/test_contrastive_demo_scenarios.py`:

### Kịch bản A: Tiệc cưới Trang trọng tại Khách sạn
* **Đầu vào Người dùng:** *"Tối nay tôi đi dự tiệc cưới trang trọng ở khách sạn, cần chỉn chu lịch thiệp"*
* **Hồ sơ được kích hoạt:** `weight_profile = "formal"`
* **Kết quả Xếp hạng Top 1:** Áo Suit Blazer Wool + Quần tây âu Wool + Giày da Oxford (`formality_level = 5`).
* **Lời giải thích của Stylist:** Phân tích sự lịch thiệp, đường may sắc nét chuẩn mực của bộ âu phục mang lại sự đĩnh đạc và tôn trọng tuyệt đối cho buổi tiệc trọng đại.

### Kịch bản B: Cà phê Dạo phố Ngày Nắng nóng 35 Độ
* **Đầu vào Người dùng:** *"Hôm nay trời nắng nóng 35 độ oi bức, tôi đi cà phê dạo phố ưu tiên thoải mái mát mẻ"*
* **Hồ sơ được kích hoạt:** `weight_profile = "comfort"`
* **Kết quả Xếp hạng Top 1:** Áo thun cotton trắng mát + Quần đũi linen xám + Giày sneaker canvas mềm (`comfort_level = 5`, `weather_suitability = hot/warm`).
* **Bằng chứng Toán học:** Dù bộ Suit Blazer ở Kịch bản A có điểm Thẩm mỹ (Aesthetic Score) rất cao, nhưng khi rơi vào Kịch bản B, do trọng số Thoải mái và Thời tiết chiếm tới 55% tổng điểm, bộ Suit bị phạt nặng về nhiệt lượng và độ cứng gò bó, nhường vị trí Quán quân Top 1 cho bộ đồ cotton/linen thoáng khí.
* **Lời giải thích của Stylist:** Phân tích độ thông thoáng của sợi vải tự nhiên (cotton/linen), gam màu sáng phản xạ nhiệt và sự thoải mái tối đa khi di chuyển dưới thời tiết nắng nóng.

---

## 5. Các Ràng buộc Bất biến Hệ thống (System Invariants)

1. **INVARIANT 1 (Mathematical Boundedness):** Mọi điểm thành phần và điểm tổng hợp luôn thuộc đoạn chuẩn hóa $[0.0, 1.0]$.
2. **INVARIANT 2 (Aesthetic Independence):** Điểm thẩm mỹ Tầng 2 không bao giờ bị biến động chỉ vì thông tin thời tiết ngoài trời thay đổi.
3. **INVARIANT 3 (Zero LLM Hallucination in Invariants):** LLM chỉ trích xuất từ khóa ngữ cảnh và sinh lời văn giải thích; toàn bộ logic lọc đồ, tính điểm, xếp hạng và ghép tổ hợp được thực hiện 100% bằng thuật toán toán học tất định (Deterministic Algorithm).
4. **INVARIANT 4 (Resilience & Offline Determinism):** Khi các dịch vụ bên thứ ba (Gemini API, Weather API) gặp sự cố (429 Rate Limit, Timeout), hệ thống lập tức kích hoạt Circuit Breaker chuyển sang chế độ dự phòng an toàn (Fallback Provider) mà không gây sập ứng dụng.
