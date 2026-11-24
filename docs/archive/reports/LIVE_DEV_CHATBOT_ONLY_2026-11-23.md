# Báo Cáo Benchmark Chất Lượng Tư Vấn Multi-Agent Chatbot

## 1. Thông Tin Đợt Chạy (Execution Metadata)

- **Dataset version:** `multi-agent-bench-v3` (Wardrobes: `stylist-wardrobes-v1`)
- **Split:** `dev` (38 representative cases; Stress cases: 0)
- **Execution mode:** `live_llm` | **Live LLM:** `True` | **Judge enabled:** `False`
- **Chatbot model:** `gemini-3.6-flash` (Gemini keys: `6`, LLM cache hits: `109`)
- **Judge model:** `disabled` (`none`) | API calls: `0` | Cache hits: `0` | Tokens (in/out): `0 / 0`
- **Git commit:** `33a0ff5` | **Timestamp:** `2026-11-23T09:06:15.529131+00:00`
- **Run complete:** `True`

## 3. Lớp A — Kiểm Định Kỹ Thuật Bắt Buộc (Technical Gate)

| Hệ thống | Case Pass Lớp A | Grounding ID | Cấu trúc bộ đồ | Tuân thủ Must-Avoid | Giải thích trung thực | Cú pháp [Ngoặc] | Bounded & Persist |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | 34/38 (89.5%) | 100.0% | 100.0% | 54.2% | 100.0% | 100.0% | 100.0% |
| **B1** | 38/38 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **M-Full** | 38/38 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **B2** | 37/38 (97.4%) | 100.0% | 100.0% | 91.7% | 100.0% | 100.0% | 100.0% |

## 4. Lớp B — Benchmark Chất Lượng Tư Vấn (5 Trục B1–B5)

| Hệ thống | Functional Pass (95% CI) | Context Acc (B1) | NDCG@3 (95% CI) | Hit@1 (>=4/5) | Unacceptable (<=2/5) | Diversity (B3) | Profile Diff (B3) | Contrastive (B3) | LLM Explain Acc (B4) | Explain Useful (1-5) | Latency P50/P95 (ms) | Avg LLM Calls |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | 21/38 (55.3%) [39.7%, 69.8%] | N/A | N/A | N/A | N/A | 0.909 | 100.0% (4/4) | 100.0% (2/2) | N/A | N/A | 3.76 / 5.61 | 0.00 |
| **B1** | 30/38 (79.0%) [63.6%, 88.9%] | 89.4% | N/A | N/A | N/A | 0.738 | 100.0% (4/4) | 100.0% (2/2) | N/A | N/A | 40.72 / 66.95 | 0.00 |
| **M-Full** | 35/38 (92.1%) [79.2%, 97.3%] | 92.3% | N/A | N/A | N/A | 0.729 | 100.0% (4/4) | 100.0% (2/2) | 99.0% | N/A | 48.13 / 85.46 | 1.90 |
| **B2** | 32/38 (84.2%) [69.6%, 92.6%] | N/A | N/A | N/A | N/A | 0.772 | 100.0% (4/4) | 100.0% (2/2) | 100.0% | N/A | 3.48 / 454.45 | 1.00 |

### 4.1. Đối chiếu Tập Dev vs Holdout (Chống Quá Khớp)

| Hệ thống | Dev Pass | Holdout Pass | Dev NDCG@3 | Holdout NDCG@3 |
| :--- | :---: | :---: | :---: | :---: |
| **B0** | 21/38 (55.3%) | 0/0 (N/A) | N/A | N/A |
| **B1** | 30/38 (79.0%) | 0/0 (N/A) | N/A | N/A |
| **M-Full** | 35/38 (92.1%) | 0/0 (N/A) | N/A | N/A |
| **B2** | 32/38 (84.2%) | 0/0 (N/A) | N/A | N/A |

## 5. Đánh Giá Giá Trị Thực Của Multi-Agent Loops (B5 — Net Loop Impact)

| Phép so sánh | Tổng case | Cải thiện (Improved) | Không đổi | Giảm chất lượng (Degraded) | Net Gain | Case cải thiện | Case tụt |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **Cyclic+LLM vs Rule-DAG (M-Full vs B1)** | 38 | 6 | 31 | 1 | +5 | r18, r41, r43, r45, r49 | r38 |

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

### `B0` — Case `r23` (rep)
- **Query:** Chiều nay đi cafe với bạn, trời mát, nên mặc gì?
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '08688643-f_drs_02' violates must_avoid color; Rank 1: item '08688643-f_ftw_05' violates must_avoid color; Rank 2: item '08688643-f_top_04' violates must_avoid color; Rank 2: item '08688643-f_bot_06' violates must_avoid color; Rank 3: item '08688643-f_drs_02' violates must_avoid color; Rank 3: item '08688643-f_acc_02' violates must_avoid color

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

### `B0` — Case `r45` (rep)
- **Query:** Tối nay đi liên hoan tất niên với team, trời hơi se lạnh.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '188fbf6a-m_ftw_05' violates must_avoid color; Rank 2: item '188fbf6a-m_ftw_05' violates must_avoid color; Rank 2: item '188fbf6a-m_acc_01' violates must_avoid color; Rank 3: item '188fbf6a-m_top_06' violates must_avoid color; Rank 3: item '188fbf6a-m_acc_01' violates must_avoid color

### `B0` — Case `r54` (rep)
- **Query:** Sáng mai đi làm văn phòng trời mát, gợi ý giúp mình một bộ gọn gàng.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 2: item '8dc20be9-m_top_06' violates must_avoid color; Rank 3: item '8dc20be9-m_top_06' violates must_avoid color; Rank 3: item '8dc20be9-m_acc_01' violates must_avoid color

### `B0` — Case `r55` (rep)
- **Query:** Sáng mai có lịch phỏng vấn quan trọng ở công ty, trời mát, chọn bộ lịch sự chưa mặc gần đây.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 avg formality 3.33 < min 3.5

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

### `B1` — Case `r49` (rep)
- **Query:** Đi làm sáng mai trời ấm, mình muốn mặc áo sơ mi trắng vải linen.
- **Status:** `error` | **Error:** `NO_COMPLETE_OUTFIT` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'error' (err=NO_COMPLETE_OUTFIT)
- **Agent Trace:** `context(CONTEXT_EXTRACTED) -> wardrobe(CANDIDATE_POOL_BUILT)`

### `B1` — Case `r50` (rep)
- **Query:** Đi làm sáng mai trời mát, mình muốn mặc quần tây màu xám.
- **Status:** `error` | **Error:** `NO_COMPLETE_OUTFIT` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'error' (err=NO_COMPLETE_OUTFIT)
- **Agent Trace:** `context(CONTEXT_EXTRACTED) -> wardrobe(CANDIDATE_POOL_BUILT)`

### `M-Full` — Case `r38` (rep)
- **Query:** Phỏng vấn sáng mai, cần mặc quần tây màu đen nhưng không mặc màu đen.
- **Status:** `clarification` | **Error:** `None` | **Context used:** `gemini`
- **Chưa đạt assertion:** Expected status='error', got 'clarification' (err=None)
- **Agent Trace:** `context(CLARIFICATION_REQUESTED)`

### `M-Full` — Case `r42` (rep)
- **Query:** Tối thứ 7 tuần này đi ăn hỏi chị họ ở nhà hàng lớn, chọn bộ thật trang nhã giúp mình.
- **Status:** `ok` | **Error:** `None` | **Context used:** `gemini`
- **Chưa đạt assertion:** Top 1 avg formality 3.00 < min 3.5
- **Agent Trace:** `context(CONTEXT_EXTRACTED) -> wardrobe(CANDIDATE_POOL_BUILT) -> fashion(EVALUATED_OUTFITS_PRODUCED) -> personalization(RANKED_OUTFITS_PRODUCED) -> coordinator(RECOMMENDATIONS_APPROVED)`

### `M-Full` — Case `r44` (rep)
- **Query:** Sáng mai đi ký hợp đồng với sếp lớn, trời mưa phùn, cần đồ gọn gàng đứng đắn.
- **Status:** `ok` | **Error:** `None` | **Context used:** `gemini`
- **Chưa đạt assertion:** Top 1 missing any required functional_flags ['water_resistant', 'rain'] (got ['light', 'work'])
- **Agent Trace:** `context(CONTEXT_EXTRACTED) -> wardrobe(CANDIDATE_POOL_BUILT) -> fashion(EVALUATED_OUTFITS_PRODUCED) -> personalization(RANKED_OUTFITS_PRODUCED) -> coordinator(RECOMMENDATIONS_APPROVED)`

### `B2` — Case `r14` (rep)
- **Query:** Tối mai đi tiệc sinh nhật, mình muốn mặc đầm nhưng không mặc màu đen.
- **Status:** `ok` | **Error:** `None` | **Context used:** `single_prompt_llm`
- **Vi phạm Lớp A:** Rank 1: item 'e4bc95af-f_ftw_02' violates must_avoid color; Rank 2: item 'e4bc95af-f_ftw_02' violates must_avoid color

### `B2` — Case `r18` (rep)
- **Query:** Đi cafe sáng mai, muốn mặc áo polo màu đen cho gọn.
- **Status:** `error` | **Error:** `NO_COMPLETE_OUTFIT` | **Context used:** `single_prompt_llm`
- **Chưa đạt assertion:** Expected status='ok', got 'error' (err=NO_COMPLETE_OUTFIT)

## 9. Giới Hạn Phương Pháp (Threats to Validity)

- Tủ đồ chuẩn (30 món nữ, 27 món nam) mô phỏng cấu trúc và tỷ lệ nhãn 'unknown' thực tế; khuyến nghị xuất thêm dữ liệu từ DB người dùng thực qua --export-wardrobe-from-db sau khi hoàn tất nạp 58 ảnh demo.
- Điểm chất lượng thời trang (Lớp B B2/B4) được chấm bởi LLM-as-a-Judge thay cho hội đồng chuyên gia dệt may chấm tay 100%; cần luôn kiểm tra cùng kết quả Calibration, Human-vs-Judge Spearman và Position Consistency.
- Quy mô mẫu 38 kịch bản (38 dev / 0 holdout) phù hợp kiểm chứng đồ án nhưng độ rộng khoảng tin cậy 95% (Wilson/Bootstrap CI) và mẫu số từng nhóm con vẫn cần được trình bày song song với tỷ lệ phần trăm.
