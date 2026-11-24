# Báo Cáo Benchmark Chất Lượng Tư Vấn Multi-Agent Chatbot

## 1. Thông Tin Đợt Chạy (Execution Metadata)

- **Dataset version:** `multi-agent-bench-v3` (Wardrobes: `stylist-wardrobes-v1`)
- **Split:** `all` (56 representative cases; Stress cases: 0)
- **Execution mode:** `live_llm` | **Live LLM:** `True` | **Judge enabled:** `True`
- **Chatbot model:** `gemini-3.6-flash` (Gemini keys: `7`, LLM cache hits: `163`)
- **Judge model:** `openai/gpt-6.1-terra` (`openai_compatible`) | Reasoning: `low` | API calls: `583` | Cache hits: `339` | Tokens (in/out): `500105 / 46531`
- **Git commit:** `0f14579` | **Timestamp:** `2026-11-23T10:52:33.872303+00:00`
- **Run complete:** `True`

## 2. Kết Quả Hiệu Chuẩn Giám Khảo (Judge Calibration)

- **Pointwise Accuracy:** `85.0%` (17/20)
- **Pairwise Bidirectional Accuracy:** `100.0%` (12/12)
- **Position Consistency Rate:** `100.0%`
- **Rubric Reference Spearman rho:** `0.9212`
- **Human vs Judge Spearman rho:** `0.9212` *(source: reference rubric rating (AI-authored baseline))*

## 3. Lớp A — Kiểm Định Kỹ Thuật Bắt Buộc (Technical Gate)

| Hệ thống | Case Pass Lớp A | Grounding ID | Cấu trúc bộ đồ | Tuân thủ Must-Avoid | Giải thích trung thực | Cú pháp [Ngoặc] | Bounded & Persist |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | 49/56 (87.5%) | 100.0% | 100.0% | 44.4% | 100.0% | 100.0% | 100.0% |
| **B1** | 56/56 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **M-Full** | 56/56 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **B2** | 54/56 (96.4%) | 100.0% | 100.0% | 94.4% | 99.3% | 99.3% | 100.0% |

## 4. Lớp B — Benchmark Chất Lượng Tư Vấn (5 Trục B1–B5)

| Hệ thống | Functional Pass (95% CI) | Context Acc (B1) | NDCG@3 (95% CI) | Hit@1 (>=4/5) | Unacceptable (<=2/5) | Diversity (B3) | Profile Diff (B3) | Contrastive (B3) | LLM Explain Acc (B4) | Explain Useful (1-5) | Latency P50/P95 (ms) | Avg LLM Calls |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | 34/56 (60.7%) [47.6%, 72.4%] | N/A | 0.344 [0.288, 0.406] | 10.7% | 16.7% | 0.904 | 100.0% (5/5) | 100.0% (3/3) | N/A | 1.90 | 3.83 / 5.61 | 0.00 |
| **B1** | 43/56 (76.8%) [64.2%, 85.9%] | 87.6% | 0.738 [0.679, 0.795] | 65.0% | 0.0% | 0.746 | 100.0% (5/5) | 100.0% (3/3) | N/A | 3.23 | 37.59 / 73.32 | 0.00 |
| **M-Full** | 52/56 (92.9%) [83.0%, 97.2%] | 92.6% | 0.742 [0.681, 0.798] | 63.5% | 0.0% | 0.737 | 100.0% (5/5) | 100.0% (3/3) | 99.4% | 3.39 | 44.99 / 69.64 | 1.93 |
| **B2** | 49/56 (87.5%) [76.4%, 93.8%] | N/A | 0.912 [0.881, 0.938] | 86.3% | 0.0% | 0.796 | 100.0% (5/5) | 100.0% (3/3) | 100.0% | 4.04 | 3.54 / 7.47 | 1.00 |

### 4.1. Đối chiếu Tập Dev vs Holdout (Chống Quá Khớp)

| Hệ thống | Dev Pass | Holdout Pass | Dev NDCG@3 | Holdout NDCG@3 |
| :--- | :---: | :---: | :---: | :---: |
| **B0** | 21/38 (55.3%) | 13/18 (72.2%) | 0.346 | 0.340 |
| **B1** | 30/38 (79.0%) | 13/18 (72.2%) | 0.708 | 0.800 |
| **M-Full** | 35/38 (92.1%) | 17/18 (94.4%) | 0.734 | 0.755 |
| **B2** | 32/38 (84.2%) | 17/18 (94.4%) | 0.912 | 0.913 |

### 4.2. So Sánh Cặp Mù 2 Chiều (M-Full vs Đối Chứng)

| Đối thủ | Số cặp | M-Full Thắng | Hòa / Bất nhất | M-Full Thua | Position Consistency |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **vs B0** | 52 | 44 (84.6%) | 0 | 8 | 100.0% |
| **vs B1** | 40 | 15 (37.5%) | 10 | 15 | 80.0% |
| **vs B2** | 49 | 10 (20.4%) | 3 | 36 | 93.9% |

## 5. Đánh Giá Giá Trị Thực Của Multi-Agent Loops (B5 — Net Loop Impact)

| Phép so sánh | Tổng case | Cải thiện (Improved) | Không đổi | Giảm chất lượng (Degraded) | Net Gain | Case cải thiện | Case tụt |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **Cyclic+LLM vs Rule-DAG (M-Full vs B1)** | 56 | 23 | 28 | 5 | +18 | r03, r04, r06, r07, r08 | r21, r23, r31, r34, r38 |

## 8. Chi Tiết Các Trường Hợp Lỗi / Fallback (Failure Breakdown)

### `B0` — Case `r01` (rep)
- **Query:** Sáng mai mình có buổi phỏng vấn xin việc ở công ty, trời mát, tư vấn giúp mình bộ đồ lịch sự nhé.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 avg formality 2.75 < min 3.5

### `B0` — Case `r02` (rep)
- **Query:** Cuối tuần này tối thứ 7 đi ăn cưới bạn thân ở khách sạn, trời mát, mặc gì cho trang trọng?
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 avg formality 3.75 < min 4.0

### `B0` — Case `r05` (rep)
- **Query:** Tối nay đi xe máy ngoài trời mưa gặp đối tác, mặc sao vừa ấm áp lại không bị ướt?
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 missing any required functional_flags ['water_resistant', 'rain'] (got ['light', 'work'])

### `B0` — Case `r14` (rep)
- **Query:** Tối mai đi tiệc sinh nhật, mình muốn mặc đầm nhưng không mặc màu đen.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '15460d2a-f_drs_02' violates must_avoid color; Rank 1: item '15460d2a-f_ftw_02' violates must_avoid color; Rank 2: item '15460d2a-f_acc_02' violates must_avoid color; Rank 3: item '15460d2a-f_acc_02' violates must_avoid color

### `B0` — Case `r15` (rep)
- **Query:** Đi cafe chiều nay với bạn, cần mặc áo polo xanh navy và đi giày sneaker trắng.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 missing item 'm_top_04' (got ['m_bot_03', 'm_ftw_01', 'm_top_01']); Top 1 missing item 'm_ftw_03' (got ['m_bot_03', 'm_ftw_01', 'm_top_01'])

### `B0` — Case `r20` (rep)
- **Query:** Sáng mai phỏng vấn cần lịch sự, tránh mặc màu nâu.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '14d0ed11-m_acc_02' violates must_avoid color; Rank 2: item '14d0ed11-m_ftw_04' violates must_avoid color; Rank 3: item '14d0ed11-m_ftw_04' violates must_avoid color

### `B0` — Case `r23` (rep)
- **Query:** Chiều nay đi cafe với bạn, trời mát, nên mặc gì?
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '08688643-f_drs_02' violates must_avoid color; Rank 1: item '08688643-f_ftw_05' violates must_avoid color; Rank 2: item '08688643-f_top_04' violates must_avoid color; Rank 2: item '08688643-f_bot_06' violates must_avoid color; Rank 3: item '08688643-f_drs_02' violates must_avoid color; Rank 3: item '08688643-f_acc_02' violates must_avoid color

### `B0` — Case `r27` (rep)
- **Query:** Tối nay đi ăn tối hẹn hò, trời mát, mặc gì hợp?
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '1702e076-m_out_02' violates must_avoid color; Rank 2: item '1702e076-m_bot_01' violates must_avoid color; Rank 2: item '1702e076-m_acc_01' violates must_avoid color; Rank 3: item '1702e076-m_ftw_05' violates must_avoid color; Rank 3: item '1702e076-m_acc_01' violates must_avoid color

### `B0` — Case `r30` (rep)
- **Query:** Trưa nay đi dạo phố, trời nắng nóng 36 độ, cần thoải mái nhẹ nhàng.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 avg formality 4.00 > max 2.5

### `B0` — Case `r31` (rep)
- **Query:** Tối nay dự đám cưới ở trung tâm hội nghị, mặc trang trọng.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 avg formality 2.25 < min 4.0

### `B0` — Case `r32` (rep)
- **Query:** Chiều nay đi xe máy ngoài trời mưa, cần đồ chống nước và dễ di chuyển.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 missing any required functional_flags ['water_resistant', 'rain'] (got ['movement', 'work'])

### `B0` — Case `r35` (rep)
- **Query:** Mặc gì?
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Expected status='clarification', got 'ok' (err=None)

### `B0` — Case `r36` (rep)
- **Query:** Ở Đà Lạt mặc gì?
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Expected status='clarification', got 'ok' (err=None)

### `B0` — Case `r37` (rep)
- **Query:** Tối nay đi tiệc trang trọng, bắt buộc mặc quần tây màu đen.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 missing item 'm_bot_01' (got ['m_acc_01', 'm_bot_04', 'm_ftw_01', 'm_top_06'])

### `B0` — Case `r38` (rep)
- **Query:** Phỏng vấn sáng mai, cần mặc quần tây màu đen nhưng không mặc màu đen.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Expected status='error', got 'ok' (err=None)

### `B0` — Case `r39` (rep)
- **Query:** Tối nay dự tiệc cưới, tôi muốn mặc đầm hoa.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Expected status='error', got 'ok' (err=None)

### `B0` — Case `r40` (rep)
- **Query:** Sáng mai đi cafe trời mát, tư vấn set đồ tránh mặc màu đen và không mặc quần jean.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '60ba1e12-f_acc_02' violates must_avoid color; Rank 2: item '60ba1e12-f_bot_06' violates must_avoid color; Rank 3: item '60ba1e12-f_top_04' violates must_avoid color; Rank 3: item '60ba1e12-f_bot_06' violates must_avoid color; Rank 3: item '60ba1e12-f_acc_02' violates must_avoid color

### `B0` — Case `r45` (rep)
- **Query:** Tối nay đi liên hoan tất niên với team, trời hơi se lạnh.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '188fbf6a-m_ftw_05' violates must_avoid color; Rank 2: item '188fbf6a-m_ftw_05' violates must_avoid color; Rank 2: item '188fbf6a-m_acc_01' violates must_avoid color; Rank 3: item '188fbf6a-m_top_06' violates must_avoid color; Rank 3: item '188fbf6a-m_acc_01' violates must_avoid color

### `B0` — Case `r48` (rep)
- **Query:** Sáng mai đi dự lễ thành hôn của đồng nghiệp thân, trời lạnh 13 độ.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 missing required outerwear slot (got ['accessory', 'dress', 'footwear'])

### `B0` — Case `r54` (rep)
- **Query:** Sáng mai đi làm văn phòng trời mát, gợi ý giúp mình một bộ gọn gàng.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 2: item '8dc20be9-m_top_06' violates must_avoid color; Rank 3: item '8dc20be9-m_top_06' violates must_avoid color; Rank 3: item '8dc20be9-m_acc_01' violates must_avoid color

### `B0` — Case `r55` (rep)
- **Query:** Sáng mai có lịch phỏng vấn quan trọng ở công ty, trời mát, chọn bộ lịch sự chưa mặc gần đây.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 avg formality 3.33 < min 3.5

### `B0` — Case `r56` (rep)
- **Query:** Tối nay đi tiệc trang trọng với công ty, trời mát, tránh mặc lại bộ hôm qua.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 avg formality 2.50 < min 3.0

### `B1` — Case `r18` (rep)
- **Query:** Đi cafe sáng mai, muốn mặc áo polo màu đen cho gọn.
- **Status:** `error` | **Error:** `NO_COMPLETE_OUTFIT` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'error' (err=NO_COMPLETE_OUTFIT)
- **Agent Trace:** `context(CONTEXT_EXTRACTED) -> wardrobe(CANDIDATE_POOL_BUILT)`

### `B1` — Case `r41` (rep)
- **Query:** Tối nay qua nhà bạn gái ăn cơm ra mắt, muốn nhìn gọn gàng chững chạc xíu đừng hầm hố quá.
- **Status:** `clarification` | **Error:** `None` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'clarification' (err=None)
- **Agent Trace:** `context(CLARIFICATION_REQUESTED)`

### `B1` — Case `r42` (rep)
- **Query:** Tối thứ 7 tuần này đi ăn hỏi chị họ ở nhà hàng lớn, chọn bộ thật trang nhã giúp mình.
- **Status:** `ok` | **Error:** `None` | **Context used:** `rules`
- **Chưa đạt assertion:** Top 1 avg formality 3.00 < min 3.5
- **Agent Trace:** `context(CONTEXT_EXTRACTED) -> wardrobe(CANDIDATE_POOL_BUILT) -> fashion(EVALUATED_OUTFITS_PRODUCED) -> personalization(RANKED_OUTFITS_PRODUCED) -> coordinator(RECOMMENDATIONS_APPROVED)`

### `B1` — Case `r43` (rep)
- **Query:** Chiều mai ra quán trà sữa ngồi làm bài tập nhóm với mấy đứa bạn, trời nóng nực quá.
- **Status:** `clarification` | **Error:** `None` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'clarification' (err=None)
- **Agent Trace:** `context(CLARIFICATION_REQUESTED)`

### `B1` — Case `r44` (rep)
- **Query:** Sáng mai đi ký hợp đồng với sếp lớn, trời mưa phùn, cần đồ gọn gàng đứng đắn.
- **Status:** `clarification` | **Error:** `None` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'clarification' (err=None)
- **Agent Trace:** `context(CLARIFICATION_REQUESTED)`

### `B1` — Case `r45` (rep)
- **Query:** Tối nay đi liên hoan tất niên với team, trời hơi se lạnh.
- **Status:** `clarification` | **Error:** `None` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'clarification' (err=None)
- **Agent Trace:** `context(CLARIFICATION_REQUESTED)`

### `B1` — Case `r46` (rep)
- **Query:** Chiều nay có lịch test chuyên môn vòng cuối ở ngân hàng, trời mát mẻ.
- **Status:** `clarification` | **Error:** `None` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'clarification' (err=None)
- **Agent Trace:** `context(CLARIFICATION_REQUESTED)`

### `B1` — Case `r47` (rep)
- **Query:** Tối mai rủ crush đi xem phim rồi ăn khuya, trời ấm áp, tư vấn bộ dễ thương gọn mắt.
- **Status:** `clarification` | **Error:** `None` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'clarification' (err=None)
- **Agent Trace:** `context(CLARIFICATION_REQUESTED)`

## 9. Giới Hạn Phương Pháp (Threats to Validity)

- Tủ đồ chuẩn (30 món nữ, 27 món nam) mô phỏng cấu trúc và tỷ lệ nhãn 'unknown' thực tế; khuyến nghị xuất thêm dữ liệu từ DB người dùng thực qua --export-wardrobe-from-db sau khi hoàn tất nạp 58 ảnh demo.
- Điểm chất lượng thời trang (Lớp B B2/B4) được chấm bởi LLM-as-a-Judge thay cho hội đồng chuyên gia dệt may chấm tay 100%; cần luôn kiểm tra cùng kết quả Calibration, Human-vs-Judge Spearman và Position Consistency.
- Quy mô mẫu 56 kịch bản (38 dev / 18 holdout) phù hợp kiểm chứng đồ án nhưng độ rộng khoảng tin cậy 95% (Wilson/Bootstrap CI) và mẫu số từng nhóm con vẫn cần được trình bày song song với tỷ lệ phần trăm.
