# Báo Cáo Benchmark Chất Lượng Tư Vấn Multi-Agent Chatbot

## 1. Thông Tin Đợt Chạy (Execution Metadata)

- **Dataset version:** `multi-agent-bench-v3` (Wardrobes: `stylist-wardrobes-v1`)
- **Split:** `all` (56 representative cases; Stress cases: 12)
- **Execution mode:** `offline_deterministic` | **Live LLM:** `False` | **Judge enabled:** `False`
- **Chatbot model:** `offline-rules`
- **Judge model:** `disabled` (`none`)
- **Git commit:** `c8ca988` | **Timestamp:** `2026-11-22T10:33:57.996064+00:00`
- **Run complete:** `True`

## 3. Lớp A — Kiểm Định Kỹ Thuật Bắt Buộc (Technical Gate)

| Hệ thống | Case Pass Lớp A | Grounding ID | Cấu trúc bộ đồ | Tuân thủ Must-Avoid | Giải thích trung thực | Cú pháp [Ngoặc] | Bounded & Persist |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | 49/56 (87.5%) | 100.0% | 100.0% | 44.4% | 100.0% | 100.0% | 100.0% |
| **B1** | 56/56 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **M-Full** | 56/56 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **M-NoLoop1** | 56/56 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **M-NoLoop2** | 56/56 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **M-NoLoops** | 56/56 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **M-NoPersonalization** | 55/56 (98.2%) | 100.0% | 100.0% | 97.0% | 100.0% | 100.0% | 100.0% |

## 4. Lớp B — Benchmark Chất Lượng Tư Vấn (5 Trục B1–B5)

| Hệ thống | Functional Pass (95% CI) | Context Acc (B1) | NDCG@3 (95% CI) | Hit@1 (>=4/5) | Unacceptable (<=2/5) | Diversity (B3) | Profile Diff (B3) | Contrastive (B3) | LLM Explain Acc (B4) | Explain Useful (1-5) | Latency P50/P95 (ms) | Avg LLM Calls |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | 34/56 (60.7%) [47.6%, 72.4%] | N/A | N/A | N/A | N/A | 0.904 | 100.0% (5/5) | 100.0% (3/3) | N/A | N/A | 3.97 / 4.97 | 0.00 |
| **B1** | 43/56 (76.8%) [64.2%, 85.9%] | 87.6% | N/A | N/A | N/A | 0.746 | 100.0% (5/5) | 100.0% (3/3) | N/A | N/A | 49.56 / 88.11 | 0.00 |
| **M-Full** | 48/56 (85.7%) [74.3%, 92.6%] | 87.6% | N/A | N/A | N/A | 0.736 | 100.0% (5/5) | 100.0% (3/3) | N/A | N/A | 47.48 / 92.29 | 0.00 |
| **M-NoLoop1** | 43/56 (76.8%) [64.2%, 85.9%] | 87.6% | N/A | N/A | N/A | 0.746 | 100.0% (5/5) | 100.0% (3/3) | N/A | N/A | 48.89 / 75.63 | 0.00 |
| **M-NoLoop2** | 48/56 (85.7%) [74.3%, 92.6%] | 87.6% | N/A | N/A | N/A | 0.736 | 100.0% (5/5) | 100.0% (3/3) | N/A | N/A | 49.83 / 85.94 | 0.00 |
| **M-NoLoops** | 43/56 (76.8%) [64.2%, 85.9%] | 87.6% | N/A | N/A | N/A | 0.746 | 100.0% (5/5) | 100.0% (3/3) | N/A | N/A | 44.13 / 88.52 | 0.00 |
| **M-NoPersonalization** | 47/56 (83.9%) [72.2%, 91.3%] | 87.6% | N/A | N/A | N/A | 0.752 | 0.0% (0/5) | 100.0% (3/3) | N/A | N/A | 50.23 / 73.69 | 0.00 |

### 4.1. Đối chiếu Tập Dev vs Holdout (Chống Quá Khớp)

| Hệ thống | Dev Pass | Holdout Pass | Dev NDCG@3 | Holdout NDCG@3 |
| :--- | :---: | :---: | :---: | :---: |
| **B0** | 21/38 (55.3%) | 13/18 (72.2%) | N/A | N/A |
| **B1** | 30/38 (79.0%) | 13/18 (72.2%) | N/A | N/A |
| **M-Full** | 33/38 (86.8%) | 15/18 (83.3%) | N/A | N/A |
| **M-NoLoop1** | 30/38 (79.0%) | 13/18 (72.2%) | N/A | N/A |
| **M-NoLoop2** | 33/38 (86.8%) | 15/18 (83.3%) | N/A | N/A |
| **M-NoLoops** | 30/38 (79.0%) | 13/18 (72.2%) | N/A | N/A |
| **M-NoPersonalization** | 32/38 (84.2%) | 15/18 (83.3%) | N/A | N/A |

## 5. Đánh Giá Giá Trị Thực Của Multi-Agent Loops (B5 — Net Loop Impact)

| Phép so sánh | Tổng case | Cải thiện (Improved) | Không đổi | Giảm chất lượng (Degraded) | Net Gain | Case cải thiện | Case tụt |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **Loop 1 (M-Full vs M-NoLoop1)** | 56 | 5 | 51 | 0 | +5 | r18, r49, r50, r51, r52 | - |
| **Loop 2 (M-Full vs M-NoLoop2)** | 56 | 0 | 56 | 0 | +0 | - | - |
| **Both Loops (M-Full vs M-NoLoops)** | 56 | 5 | 51 | 0 | +5 | r18, r49, r50, r51, r52 | - |
| **Cyclic+LLM vs Rule-DAG (M-Full vs B1)** | 56 | 5 | 51 | 0 | +5 | r18, r49, r50, r51, r52 | - |
| **Personalization (M-Full vs M-NoPersonalization)** | 56 | 1 | 55 | 0 | +1 | r23 | - |

## 6. Độ Bền Trước Nhiễu Nhãn Số Hóa (Noise Robustness)

| Hệ thống | Lớp A Sạch -> Nhiễu | Functional Pass Sạch -> Nhiễu | Chênh lệch | Top-1 Ổn Định (Flip Rate) | Top-1 Core Jaccard |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **B0** | 87.5% -> 87.5% | 60.7% -> 60.7% | 0.0% | 100.0% (flip 0.0%) | 1.000 |
| **B1** | 100.0% -> 100.0% | 76.8% -> 76.8% | 0.0% | 70.0% (flip 30.0%) | 0.792 |
| **M-Full** | 100.0% -> 100.0% | 85.7% -> 85.7% | 0.0% | 73.3% (flip 26.7%) | 0.815 |
| **M-NoLoop1** | 100.0% -> 100.0% | 76.8% -> 76.8% | 0.0% | 70.0% (flip 30.0%) | 0.792 |
| **M-NoLoop2** | 100.0% -> 100.0% | 85.7% -> 85.7% | 0.0% | 73.3% (flip 26.7%) | 0.815 |
| **M-NoLoops** | 100.0% -> 100.0% | 76.8% -> 76.8% | 0.0% | 70.0% (flip 30.0%) | 0.792 |
| **M-NoPersonalization** | 98.2% -> 98.2% | 83.9% -> 83.9% | 0.0% | 80.0% (flip 20.0%) | 0.844 |

## 7. Tập Chẩn Đoán Kỹ Thuật Tách Biệt (Diagnostic Stress Suite — 12 Cases)

> Lưu ý: Bảng này tách riêng khỏi 56 kịch bản đại diện ở trên, dùng để xác nhận các cơ chế Loop 1, Loop 2, Score-Drop Guard và Early Exit hoạt động đúng đặc tả.

| Hệ thống | Lớp A Pass | Stress Case Pass | Loop 1 Triggered | Loop 2 Triggered |
| :--- | :---: | :---: | :---: | :---: |
| **B0** | 12/12 | 0/12 (0.0%) | 0 | 0 |
| **B1** | 12/12 | 4/12 (33.3%) | 0 | 0 |
| **M-Full** | 12/12 | 12/12 (100.0%) | 5 | 4 |
| **M-NoLoop1** | 12/12 | 8/12 (66.7%) | 0 | 4 |
| **M-NoLoop2** | 12/12 | 8/12 (66.7%) | 5 | 0 |
| **M-NoLoops** | 12/12 | 4/12 (33.3%) | 0 | 0 |
| **M-NoPersonalization** | 12/12 | 8/12 (66.7%) | 5 | 0 |

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
