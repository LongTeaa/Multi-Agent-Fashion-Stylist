# Review toàn dự án và đề xuất nâng cấp — 18/11/2026

Người đọc: nhóm thực hiện đề tài, làm đầu vào cho kế hoạch nâng cấp "làm rõ sức mạnh multi-agent". Mọi kết luận dưới đây dựa trên lệnh đã chạy hoặc đoạn code đã đọc. Những chỗ chưa kiểm chứng được ghi rõ.

## 1. Tóm tắt

Nền tảng kỹ thuật tốt: 780 test backend và 123 test frontend đều pass, các bất biến grounding, ownership và idempotency được kiểm thử kỹ. Điểm yếu nằm ở bốn chỗ mà hội đồng dễ hỏi nhất:

1. **"Multi-agent" hiện là pipeline 5 hàm tất định chạy tuần tự.** Chỉ Context Agent gọi LLM. Không agent nào tự quyết định, phản biện hay gọi lại agent khác. Phần giải thích là template cố định.
2. **Mô hình 5 thuộc tính của giảng viên gần như không chạy trên dữ liệu demo.** 13/19 món trong DB, gồm toàn bộ tủ đồ golden, mang giá trị mặc định (comfort 3, silhouette 3, không có functional flag).
3. **Số liệu đánh giá chưa đo năng lực thật.** "Vision 100%" lấy từ provider giả trả về đáp án định sẵn. Bộ ảnh thật chỉ có 7 ảnh. Chưa có baseline nào để so sánh.
4. **Try-on không đạt mức sản phẩm.** Hệ thống gọi Hugging Face Space công khai có quota, chạy đồng bộ dù contract ghi async, chỉ ghép áo trong và quần. Ảnh avatar bị gửi cho bên thứ ba trong khi điều khoản ghi "chỉ lưu trong tài khoản".

| Mảng | Đánh giá | Ưu tiên |
| :--- | :--- | :---: |
| Kiến trúc multi-agent | Đúng cấu trúc, thiếu tính "agent" | P1 |
| Chất lượng xếp hạng | Sai ở ngữ cảnh trang trọng; dữ liệu thuộc tính trống | P1 |
| Số hóa tủ đồ | Pipeline vững; detector local yếu; chưa tách nền | P1–P3 |
| Try-on | Phạm vi hẹp, đồng bộ, rủi ro quyền riêng tư | P1 |
| Đánh giá / benchmark | Tự đánh giá trên dữ liệu tự tạo, không baseline | P1 |
| Kỹ thuật chung | Thiếu CI, Docker, xác thực thật | P2–P3 |

## 2. Những gì đã chạy

| Kiểm tra | Kết quả |
| :--- | :--- |
| `pytest backend/tests -m "not live_provider"` | 780 passed, 32 warnings, 10 phút 32 giây |
| `npx vitest run` (frontend, từ `D:\`) | 16 file, 123 passed |
| `npx eslint .` | 1 lỗi đã biết: `react-hooks/set-state-in-effect` tại `TryOnModal.tsx:233` |
| YOLO-World local trên 7 ảnh thật có annotation (`vision_real_review_v2.json`), IoU ≥ 0,5 | Precision 0,67, recall 0,60, nhãn đúng 4/6 vùng khớp, khoảng 0,2 giây/ảnh |
| Gemini (`gemini-3.6-flash`) trên cùng bộ ảnh | Ảnh đầu khớp 2/2 vùng (YOLO: 1/2); từ ảnh thứ hai bị HTTP 429 trên cả 3 key, nên dừng |
| `backend/scripts/evaluate_real_ingestion.py --live` | Hỏng ở bước replay offline, trước khi gọi provider (xem C4) |
| Chạy graph gợi ý trên bản sao DB, 7 câu hỏi, context `fallback` | Kết quả ở mục A2, A3 |

## 3. Phát hiện và hướng xử lý

Mức độ: **P1** ảnh hưởng trực tiếp tới luận điểm bảo vệ hoặc an toàn dữ liệu; **P2** sai về chất lượng hoặc độ tin cậy; **P3** tính chuyên nghiệp.

### A. Multi-agent (trọng tâm đề tài)

**A1 (P1) — Các agent không thực sự "agentic".** `backend/app/agents/stylist_graph.py` là chuỗi `context → wardrobe → fashion → personalization → coordinator`. Mỗi cạnh điều kiện chỉ dùng để thoát sớm khi có lỗi. LLM chỉ xuất hiện trong `context_agent.py`. Câu hỏi dễ gặp từ hội đồng: "nếu gộp năm hàm này thành một thì khác gì?". Hiện chưa có bằng chứng nào trả lời câu này.

Hướng xử lý: giữ nguyên lõi tất định (đây là điểm mạnh về grounding), rồi thêm các hành vi chỉ kiến trúc nhiều agent mới làm được:

- **Vòng phản biện có giới hạn (critic loop).** Khi Fashion hoặc Personalization chấm điểm top-1 dưới ngưỡng, hoặc phát hiện vi phạm (sai mức trang trọng, không hợp thời tiết), Coordinator gửi yêu cầu sửa cụ thể về Wardrobe Agent, ví dụ "cần áo có formality ≥ 4" hoặc "cần lớp ngoài chống mưa". Wardrobe Agent truy xuất lại và vòng lặp chạy tối đa 2 lần. LangGraph hỗ trợ sẵn cạnh vòng.
- **Wardrobe Gap Agent.** Khi không có bộ nào đạt ngưỡng (ví dụ "đi leo núi, trời mưa" chỉ đạt 0,345), agent này nói rõ tủ đồ thiếu món gì thay vì trả về một bộ điểm thấp. Việc này không vi phạm phạm vi vì không gợi ý mua sắm, chỉ nêu loại đồ còn thiếu.
- **Stylist Explanation Agent dùng LLM có hậu kiểm.** LLM viết lời giải thích từ dữ liệu điểm thành phần (màu, tỷ lệ, thời tiết, hồ sơ trọng số). Một bước kiểm tra tất định từ chối câu nào nhắc tới món đồ, màu hoặc chất liệu không có trong outfit, và khi đó dùng lại template. Cách này giữ được bất biến "LLM không bịa món đồ".
- **Thực thi song song.** Weather lookup và tải hồ sơ cá nhân hóa có thể fan-out song song, giúp cho thấy lợi ích về độ trễ.
- **Agent trace trên giao diện.** Hiển thị từng bước: agent nào chạy, mất bao lâu, đầu vào và đầu ra tóm tắt, vòng lặp nào đã xảy ra. Đây là cách trực quan nhất để chứng minh sức mạnh multi-agent khi demo.

Cần quyết định trước: thesis mục 3.1 và `SYSTEM_ARCHITECTURE.md` ghi "định tuyến động nằm ngoài MVP". Vòng phản biện là một dạng định tuyến động, nên cần cập nhật phạm vi thesis trước khi làm.

**A2 (P1) — Lời giải thích không nói vì sao.** Hàm `generate_grounded_explanation_vi` (`backend/app/agents/coordinator.py:259`) chỉ liệt kê món đồ và một câu về mức trang trọng. Đầu ra thật cho câu "Hôm nay trời nắng nóng 35 độ, đi dạo phố, ưu tiên thoải mái":

> Phối [Áo thun xám], [Quần short], [Giày sneaker trắng]. Các món chính đều nằm trong mức trang trọng bạn cần. Độ phù hợp ở mức vừa phải (51%); bạn nên cân nhắc theo nhu cầu.

Lời giải thích không nhắc tới thời tiết, hồ sơ "comfort" đang được dùng hay độ hài hòa màu. Tiêu chí nghiệm thu ở giai đoạn 5–6 của kế hoạch giảng viên ("lời giải thích nêu bật lý do theo trọng số ưu tiên") đã được tick đạt nhưng code chưa làm. Hướng xử lý: xem Stylist Explanation Agent ở A1. Tối thiểu, template phải nêu yếu tố có trọng số cao nhất và điểm thành phần tương ứng.

**A3 (P2) — Sai ở ngữ cảnh trang trọng và điểm hòa.** Kết quả trên tủ đồ golden:

| Câu hỏi | Hồ sơ | Top 1 | Ghi chú |
| :--- | :--- | :--- | :--- |
| Sáng mai phỏng vấn xin việc ở ngân hàng | formal | Áo Polo trắng + Quần tây đen + Giày Oxford nâu (0,876) | Hòa điểm tuyệt đối với áo sơ mi đen; giải thích tự nhận "chưa đồng đều" |
| Cuối tuần đi đám cưới bạn thân ở nhà hàng | formal | Giống trên | Polo đứng đầu ở đám cưới |
| Tối nay tôi đi cafe với bạn, trời mát | comfort | Polo + Chinos + Sneaker (0,881) | Đúng golden; hòa điểm với sơ mi đen |

Nguyên nhân gồm hai phần. Dữ liệu seed gán áo sơ mi đen formality 3, bằng polo. Đồng thời, hồ sơ formal không loại hoặc phạt đủ mạnh món nằm dưới khoảng trang trọng yêu cầu (`[4, 5]`). Hướng xử lý: sửa dữ liệu seed (xem B1); với hồ sơ formal, phạt rõ món chính thấp hơn cận dưới; thêm quy tắc phá hòa có giải thích được; thêm test hồi quy "phỏng vấn → sơ mi xếp trên polo".

**A4 (P3) — Thiếu quan sát và hiệu năng graph.** Graph được compile lại ở mỗi request (`create_stylist_graph` bên trong `execute_stylist_recommendation`). Không có thời gian chạy theo từng agent trong state hay log. Hướng xử lý: compile một lần rồi tái sử dụng, ghi `agent_trace` (tên agent, thời gian, số ứng viên vào/ra) vào state, và trả về qua API ở chế độ debug hoặc demo.

### B. Dữ liệu và mô hình 5 thuộc tính

**B1 (P1) — Mô hình của giảng viên không có dữ liệu để chạy.** Trong `data/fashion_stylist.db` có 19 món đang hoạt động. 13 món (8 món golden và cả 5 món một người dùng tải lên ngày 20/09) mang `comfort_level=3`, `silhouette_level=3`, `functional_flags=[]`. Khi mọi món giống nhau ở các chiều này, Proportion Balance, Weather & Comfort Fit và Functional Fit trở thành hằng số. Kịch bản đối chứng chỉ pass trên fixture riêng trong `test_contrastive_demo_scenarios.py`. Hướng xử lý:

- Cập nhật tủ đồ golden trong seed với giá trị thực tế (sơ mi formality 4, quần short comfort 5, v.v.).
- Viết script backfill: chạy lại trích xuất thuộc tính cho các món đang có giá trị mặc định, đưa kết quả về màn kiểm duyệt cho người dùng xác nhận, không ghi đè tự động.
- Theo dõi chỉ số "độ đầy đủ hồ sơ" (tỷ lệ món có thuộc tính khác mặc định).

**B2 (P2) — Dữ liệu thật quá nhỏ.** 19 món của 3 người dùng, không có đầm, áo khoác hay phụ kiện. Vì vậy nhánh `dress`, phối lớp ngoài và try-on phụ kiện chưa từng được thử trên dữ liệu thật. Hướng xử lý: xây một tủ đồ demo 40–60 món chụp thật, phủ đủ 6 danh mục, gồm cả ảnh một món, nhiều món, outfit đang mặc và ảnh chất lượng kém. Bộ này dùng chung cho benchmark (mục E).

### C. Số hóa tủ đồ

**C1 (P1) — Detector local đang dùng yếu hơn Gemini ở ảnh đơn món.** Cấu hình local là `DETECTOR_BACKEND=yolo_world`. Kết quả trên 7 ảnh thật:

| Ảnh | YOLO-World | Ghi chú |
| :--- | :--- | :--- |
| worn-trousers | 1/2 vùng | Trả 3 box (`jacket`, `t-shirt`, `trousers`); khớp quần, bỏ sót giày |
| matching-sneaker-pair | 0/1 | `cluttered`, không có box |
| worn-polo | 3/3 | Tốt |
| single-derby | 1/1 | |
| single-jeans | 1/1 | Gán nhãn `coat`, phân loại `worn_outfit` |
| blue-tshirt, red-tshirt | 0/1 mỗi ảnh | Không có box, rơi về chọn cả ảnh |

Khi không có box, người dùng nhận cảnh báo "ảnh nền phức tạp hoặc nhiều chi tiết" dù đó là ảnh áo phẳng nền sạch. Theo báo cáo 02/11 (`REAL_IMAGE_INGESTION_REVIEW_2026-11-02.md`), Gemini khớp các ảnh đơn món này.

Hướng xử lý: chọn detector theo số đo, không theo cảm tính. Các ứng viên nên so sánh trên cùng benchmark (mục E2):

- Gemini làm chính, YOLO-World làm dự phòng khi 429 hoặc offline.
- Detector chuyên thời trang, ví dụ mô hình YOLO huấn luyện trên DeepFashion2 (13 lớp trang phục).
- Grounding DINO hoặc Florence-2 cho phát hiện theo từ vựng mở.
- Với ảnh được xác định là đơn món, nên coi cả ảnh là một món hợp lệ thay vì cảnh báo nền phức tạp.

**C2 (P2) — Quota Gemini là rủi ro demo.** Ba key xoay vòng vẫn bị 429 ngay từ lượt gọi thứ hai. Hướng xử lý: dùng gói trả phí (hoặc tín dụng Google Cloud cho sinh viên) cho buổi demo và đợt đánh giá. Hiển thị rõ trạng thái "đang dùng chế độ dự phòng" trên UI.

**C3 (P2) — Chưa tách nền món đồ.** Crop là hình chữ nhật còn nguyên nền (`crop_engine.py`), nên thẻ tủ đồ và moodboard trông kém chuyên nghiệp và đầu vào try-on bị nhiễu. Hướng xử lý: tạo thêm ảnh cutout nền trong suốt bằng mô hình tách nền (BiRefNet, rembg) hoặc SAM 2 dùng box của detector làm prompt. Vẫn giữ crop gốc, và lưu thêm vai trò media mới. Việc này cần cập nhật `DATA_SCHEMA.md` và `OBJECT_STORAGE_SPEC.md`.

**C4 (P2) — Script đánh giá ảnh thật bị hỏng.** `evaluate_real_ingestion.py` dừng tại `confirm_ingestion_batch` với lỗi "Danh mục trang phục là bắt buộc", vì provider replay không trả `category`. Script này không nằm trong test nên không ai phát hiện. Hướng xử lý: replay trả category theo annotation, và thêm một test nhỏ chạy script ở chế độ replay.

**C5 (P3) — Không phát hiện món trùng.** Tải lại cùng một món sẽ tạo món mới. Hướng xử lý: so khớp perceptual hash hoặc embedding (ví dụ Marqo-FashionSigLIP) để cảnh báo "có thể đã có món này". Embedding này cũng dùng được cho truy xuất ngữ nghĩa sau này.

### D. Phòng thử đồ

**D1 (P1) — Quyền riêng tư ảnh avatar.** Ảnh avatar của người dùng được gửi tới Space công khai `fashn-ai/fashn-vton-1.5` qua `gradio_client` (`fashn_tryon_provider.py`). Trong khi đó, ô đồng ý ghi "Ảnh chỉ được lưu trong tài khoản của tôi" và được **tick sẵn** (`useState(true)`, `TryOnModal.tsx:85`). `VIRTUAL_TRYON_SPEC.md` yêu cầu người dùng đồng ý một cách chủ động. Hướng xử lý (làm ngay, ít tốn công): bỏ tick mặc định; nêu rõ ảnh được gửi tới dịch vụ xử lý bên ngoài; chuyển sang API thương mại có điều khoản xử lý dữ liệu (xem D3).

**D2 (P1) — Chạy đồng bộ, không có timeout thật.** `POST /tryons` là hàm đồng bộ và chạy tối đa 2 lượt FASHN liên tiếp. `API_CONTRACT.md` mô tả luồng async `202 processing`. `timeout_seconds` của provider chỉ được lưu lại mà không truyền vào `client.predict`, nên khi hàng đợi ZeroGPU bị kẹt, request có thể treo vô hạn. Hướng xử lý: trả `202` và xử lý nền, frontend poll `GET /tryons/{id}`, áp timeout thật cho cả lượt gọi.

**D3 (P2) — Phạm vi ghép đồ hẹp.** Chỉ ghép áo trong và quần, hoặc đầm. Áo khoác, giày, túi và phụ kiện chỉ hiện thành thẻ bên cạnh. Mô hình FASHN VTON 1.5 chỉ hỗ trợ `tops`, `bottoms`, `one-pieces`.

Các phương án:

| Phương án | Phủ giày/túi | Một lượt cả outfit | Ưu điểm | Nhược điểm |
| :--- | :---: | :---: | :--- | :--- |
| **Gemini 3 Pro Image** (Nano Banana Pro), tối đa 14 ảnh tham chiếu | Có | Có | Dùng lại key Gemini và `gemini_image_provider.py` đã có; một lượt gọi | Không cam kết giữ đúng chi tiết món đồ hay gương mặt; là sinh ảnh, không phải VTON chuyên dụng |
| **FASHN API Try-On Max** (Preview) | Có: giày, mũ, trang sức, túi | Không: một sản phẩm mỗi lượt | Độ trung thực cao; 1–5 credit/ảnh, khoảng 10–55 giây | Phải chạy chuỗi 4–5 lượt cho một outfit; trả phí; còn Preview |
| FASHN API v1.6 | Không | Không | 1 credit/ảnh, ổn định | Giống hiện tại về phạm vi |
| OmniTry (NeurIPS 2025, mã nguồn mở) | Có: giày, trang sức, túi | Không | Hợp góc độ nghiên cứu, tự chủ | Cần GPU; chất lượng mức nghiên cứu; tác giả nêu túi còn khó |
| Vertex AI Virtual Try-On | Chưa xác minh được | — | Hạ tầng Google | Không tìm thấy tài liệu chính thức xác nhận hỗ trợ giày hay phụ kiện |

Khuyến nghị: dùng API thay vì Space công khai. Phương án hợp nhất với đề tài:

1. **Gemini 3 Pro Image làm đường chính**, một lượt gọi với ảnh avatar và cutout của tất cả món (kể cả giày và túi). Gắn nhãn "Ảnh minh họa AI".
2. **Thêm Try-On QA Agent**: một lượt Gemini Vision so ảnh kết quả với từng cutout và trả về danh sách món thiếu hoặc sai màu. Nếu sai, sinh lại một lần với chỉ dẫn sửa; vẫn sai thì báo rõ cho người dùng. Agent này vừa nâng chất lượng vừa là ví dụ cụ thể cho phối hợp nhiều agent.
3. Giữ FASHN (bản API) làm tùy chọn "độ trung thực cao" cho áo, quần và đầm nếu có ngân sách.
4. Moodboard vẫn là dự phòng cuối cùng, như hiện tại.

Trước khi chọn, cần chạy thử nghiệm nhỏ (khoảng 10 outfit × 2 avatar) và chấm theo các tiêu chí ở mục E3.

### E. Đánh giá và benchmark

**E1 (P1) — Số liệu thesis 6.1.1 chưa đo năng lực thật.**

- "Vision 100%" dùng `FakeVisionProvider` trả thuộc tính theo kịch bản định sẵn (`test_acceptance_metrics.py`), nên chỉ kiểm tra bước chuẩn hóa.
- Context F1 87,33% đo bộ phân tích quy tắc trên 30 câu do chính nhóm viết.
- Retrieval Recall@10 100% đo trên tủ đồ tổng hợp.
- Không có baseline, nên không có con số nào cho thấy multi-agent tốt hơn cách khác.

Thesis có ghi chú các giới hạn này, nhưng bảng kết quả vẫn dễ bị chất vấn.

**E2 — Đề xuất bộ benchmark** (đề xuất mới, chưa thực hiện):

| Thành phần | Dữ liệu | Chỉ số |
| :--- | :--- | :--- |
| Phát hiện món đồ | ≥ 100 ảnh thật, đủ 4 loại cảnh (một món, nhiều món, đang mặc, chất lượng kém). Hai người gán nhãn độc lập, không xem trước dự đoán | Recall/precision ở IoU 0,5, độ đồng thuận giữa người gán nhãn (Cohen's kappa); so YOLO-World, Gemini và một detector chuyên thời trang |
| Thuộc tính | Cùng bộ ảnh, nhãn danh mục, màu, formality, comfort, silhouette, độ dài | Accuracy từng trường; sai số tuyệt đối trung bình (MAE) cho thang 1–5 |
| Hiểu ngữ cảnh | 100+ câu: diễn đạt khác nhau, không dấu ("toi nay di cafe"), lỗi gõ, câu mơ hồ | F1 từng trường; so `fallback` với Gemini |
| Gợi ý phối đồ | 50–100 tình huống × 3–5 tủ đồ demo | Xem E3 |
| Try-on | 10–20 outfit × 2 avatar | Tỷ lệ món hiển thị đúng, giữ màu và họa tiết, giữ gương mặt; chuyên gia chấm 1–5 |
| Hệ thống | Mọi luồng chạy với provider thật | p50/p95 theo từng agent; chi phí API mỗi request |

**E3 — Thí nghiệm chứng minh sức mạnh multi-agent (ablation):**

| Cấu hình | Mô tả |
| :--- | :--- |
| B0 — Một LLM | Đưa toàn bộ tủ đồ và câu hỏi cho Gemini, yêu cầu chọn outfit |
| B1 — Luật thuần | Chỉ dùng lọc và chấm điểm tất định, không Context LLM, không vòng phản biện |
| M — Multi-agent hiện tại | Pipeline 5 agent |
| M+ — Multi-agent nâng cấp | Có vòng phản biện, Gap Agent, Explanation Agent |
| M+ trừ từng agent | Bỏ lần lượt Personalization, Fashion, critic loop |

Chỉ số:

- **Grounding rate:** B0 dự kiến sẽ bịa món hoặc ID; đây là bằng chứng mạnh cho kiến trúc.
- **Tỷ lệ thỏa ràng buộc:** formality, thời tiết, điều cần tránh.
- **Điểm chuyên gia 1–5:** giảng viên hoặc sinh viên ngành Thời trang chấm mù, thứ tự ngẫu nhiên.
- **LLM-as-judge:** chỉ dùng làm thước đo phụ, đối chiếu với điểm chuyên gia.
- **Độ đa dạng, độ trễ, chi phí.**

Bộ Polyvore Outfits (bài toán đánh giá độ hợp và FITB) có thể dùng để kiểm tra riêng phần chấm điểm thẩm mỹ, nhưng cần nói rõ khác miền dữ liệu.

**E4 — Đánh giá người dùng:** 10–15 người dùng làm bộ nhiệm vụ (số hóa 5 món, hỏi 3 tình huống, thử đồ), đo thời gian hoàn thành và điểm SUS.

### F. Kỹ thuật và tính chuyên nghiệp

| ID | Mức | Vấn đề | Hướng xử lý |
| :--- | :---: | :--- | :--- |
| F1 | P2 | Danh tính người dùng là header `X-User-Id` do client tự gửi; ai biết UUID đều mạo danh được | Đăng nhập thật (Auth.js/NextAuth hoặc JWT); tối thiểu ghi rõ là giới hạn demo |
| F2 | P2 | Không có CI (`.github/` không tồn tại); 780 test chỉ chạy tay | GitHub Actions: backend unit+contract, frontend vitest+tsc+lint, `verify_documentation.ps1`; bộ đầy đủ chạy hằng đêm |
| F3 | P3 | `compose.yaml` chỉ có MinIO; không có Dockerfile cho backend và frontend | Dockerfile + compose cho toàn hệ thống để demo bằng một lệnh |
| F4 | P3 | Test backend mất 10,5 phút | Đánh dấu test chậm, chạy song song bằng `pytest-xdist` |
| F5 | P3 | Tác vụ nền dùng `BackgroundTasks` trong tiến trình, mất khi restart | Chấp nhận cho đồ án; chỉ đổi sang hàng đợi (arq/RQ) nếu còn thời gian |
| F6 | P3 | Lỗi lint `TryOnModal.tsx:233` | Sửa khi đụng tới try-on |

## 4. Thứ tự đề xuất

Đo trước, nâng cấp sau. Nếu không có benchmark từ đầu sẽ không chứng minh được cải tiến.

1. **Sửa nhanh (1–2 ngày):** D1 (đồng ý chủ động), D2 (timeout), C4, A3 (seed và quy tắc formal), B1 (seed golden).
2. **Nền tảng đánh giá:** tủ đồ demo thật (B2), bộ benchmark E2, chạy baseline B0/B1/M để có số "trước".
3. **Nâng cấp multi-agent:** A1 (critic loop, Gap Agent, Explanation Agent, agent trace), A2, A4.
4. **Try-on qua API + Try-On QA Agent (D3),** chạy song song với bước 3 nếu có người.
5. **Chất lượng số hóa:** chọn detector theo benchmark (C1), tách nền (C3), chống trùng (C5).
6. **Chuyên nghiệp hóa:** CI, Docker, xác thực (F1–F3).
7. **Đánh giá cuối:** ablation E3, chuyên gia chấm, người dùng E4; cập nhật thesis chương 6 (T-1, T-2 trong `ALIGNMENT_BACKLOG.md`).

## 5. Cần quyết định

- Mở rộng phạm vi thesis để cho phép vòng phản biện (định tuyến động có giới hạn).
- Ngân sách API cho Gemini trả phí và/hoặc FASHN API, cho demo và đợt đánh giá.
- Thay Space FASHN công khai bằng API có điều khoản xử lý dữ liệu.
- Nguồn chuyên gia chấm điểm (giảng viên hoặc sinh viên ngành Thời trang) và số lượng.

## 6. Nguồn tham khảo

- FASHN Try-On Max API: <https://docs.fashn.ai/api-reference/tryon-max>
- FASHN Try-On v1.6 API: <https://docs.fashn.ai/api-reference/tryon-v1-6>
- Gemini 3 Pro Image trên Vertex AI: <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-pro-image>
- Nano Banana Pro cho doanh nghiệp: <https://cloud.google.com/blog/products/ai-machine-learning/nano-banana-pro-available-for-enterprise>
- Vertex AI Virtual Try-On API: <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/virtual-try-on-api>
- OmniTry: Virtual Try-On Anything without Masks: <https://arxiv.org/abs/2508.13632>
- Marqo-FashionCLIP / FashionSigLIP: <https://github.com/marqo-ai/marqo-FashionCLIP>
- Tổng hợp API try-on 2026 (bên thứ ba): <https://fal.ai/learn/tools/best-virtual-try-on-apis-2026>
