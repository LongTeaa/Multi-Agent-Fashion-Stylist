# Báo Cáo Benchmark Chất Lượng Tư Vấn Multi-Agent Chatbot

## 1. Thông Tin Đợt Chạy (Execution Metadata)

- **Dataset version:** `multi-agent-bench-v3` (Wardrobes: `stylist-wardrobes-v1`)
- **Split:** `holdout` (18 representative cases; Stress cases: 0)
- **Execution mode:** `live_llm` | **Live LLM:** `True` | **Judge enabled:** `True`
- **Chatbot model:** `gemini-3.6-flash` (Gemini keys: `7`, LLM cache hits: `3`)
- **Judge model:** `openai/gpt-6.1-terra` (`openai_compatible`) | Reasoning: `low` | API calls: `294` | Cache hits: `44` | Tokens (in/out): `250538 / 24282`
- **Git commit:** `0f14579` | **Timestamp:** `2026-11-23T10:13:20.937462+00:00`
- **Run complete:** `True`

## 2. Kết Quả Hiệu Chuẩn Giám Khảo (Judge Calibration)

- **Pointwise Accuracy:** `85.0%` (17/20)
- **Pairwise Bidirectional Accuracy:** `100.0%` (12/12)
- **Position Consistency Rate:** `100.0%`
- **Rubric Reference Spearman rho:** `0.9212`
- **Human vs Judge Spearman rho:** `0.8953` *(source: blind human raters (n=3))*

## 3. Lớp A — Kiểm Định Kỹ Thuật Bắt Buộc (Technical Gate)

| Hệ thống | Case Pass Lớp A | Grounding ID | Cấu trúc bộ đồ | Tuân thủ Must-Avoid | Giải thích trung thực | Cú pháp [Ngoặc] | Bounded & Persist |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | 15/18 (83.3%) | 100.0% | 100.0% | 25.0% | 100.0% | 100.0% | 100.0% |
| **B1** | 18/18 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **M-Full** | 18/18 (100.0%) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **B2** | 17/18 (94.4%) | 100.0% | 100.0% | 100.0% | 98.0% | 98.0% | 100.0% |

## 4. Lớp B — Benchmark Chất Lượng Tư Vấn (5 Trục B1–B5)

| Hệ thống | Functional Pass (95% CI) | Context Acc (B1) | NDCG@3 (95% CI) | Hit@1 (>=4/5) | Unacceptable (<=2/5) | Diversity (B3) | Profile Diff (B3) | Contrastive (B3) | LLM Explain Acc (B4) | Explain Useful (1-5) | Latency P50/P95 (ms) | Avg LLM Calls |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | 13/18 (72.2%) [49.1%, 87.5%] | N/A | 0.345 [0.250, 0.447] | 16.7% | 18.5% | 0.896 | 100.0% (1/1) | 100.0% (1/1) | N/A | 1.89 | 4.91 / 7.48 | 0.00 |
| **B1** | 13/18 (72.2%) [49.1%, 87.5%] | 84.1% | 0.806 [0.689, 0.890] | 69.2% | 0.0% | 0.762 | 100.0% (1/1) | 100.0% (1/1) | N/A | 3.22 | 43.2 / 75.23 | 0.00 |
| **M-Full** | 17/18 (94.4%) [74.2%, 99.0%] | 93.2% | 0.759 [0.661, 0.846] | 61.1% | 0.0% | 0.753 | 100.0% (1/1) | 100.0% (1/1) | 100.0% | 3.39 | 23408.96 / 40917.04 | 2.00 |
| **B2** | 16/18 (88.9%) [67.2%, 96.9%] | N/A | 0.911 [0.873, 0.946] | 82.3% | 0.0% | 0.836 | 100.0% (1/1) | 100.0% (1/1) | 100.0% | 3.93 | 9262.97 / 24272.92 | 1.00 |

### 4.1. Đối chiếu Tập Dev vs Holdout (Chống Quá Khớp)

| Hệ thống | Dev Pass | Holdout Pass | Dev NDCG@3 | Holdout NDCG@3 |
| :--- | :---: | :---: | :---: | :---: |
| **B0** | 0/0 (N/A) | 13/18 (72.2%) | N/A | 0.345 |
| **B1** | 0/0 (N/A) | 13/18 (72.2%) | N/A | 0.806 |
| **M-Full** | 0/0 (N/A) | 17/18 (94.4%) | N/A | 0.759 |
| **B2** | 0/0 (N/A) | 16/18 (88.9%) | N/A | 0.911 |

### 4.2. So Sánh Cặp Mù 2 Chiều (M-Full vs Đối Chứng)

| Đối thủ | Số cặp | M-Full Thắng | Hòa / Bất nhất | M-Full Thua | Position Consistency |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **vs B0** | 18 | 15 (83.3%) | 0 | 3 | 100.0% |
| **vs B1** | 13 | 7 (53.8%) | 3 | 3 | 84.6% |
| **vs B2** | 17 | 4 (23.5%) | 0 | 13 | 100.0% |

## 5. Đánh Giá Giá Trị Thực Của Multi-Agent Loops (B5 — Net Loop Impact)

| Phép so sánh | Tổng case | Cải thiện (Improved) | Không đổi | Giảm chất lượng (Degraded) | Net Gain | Case cải thiện | Case tụt |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **Cyclic+LLM vs Rule-DAG (M-Full vs B1)** | 18 | 9 | 7 | 2 | +7 | r09, r12, r20, r33, r46 | r28, r34 |

## 8. Chi Tiết Các Trường Hợp Lỗi / Fallback (Failure Breakdown)

### `B0` — Case `r20` (rep)
- **Query:** Sáng mai phỏng vấn cần lịch sự, tránh mặc màu nâu.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '14d0ed11-m_acc_02' violates must_avoid color; Rank 2: item '14d0ed11-m_ftw_04' violates must_avoid color; Rank 3: item '14d0ed11-m_ftw_04' violates must_avoid color

### `B0` — Case `r27` (rep)
- **Query:** Tối nay đi ăn tối hẹn hò, trời mát, mặc gì hợp?
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '1702e076-m_out_02' violates must_avoid color; Rank 2: item '1702e076-m_bot_01' violates must_avoid color; Rank 2: item '1702e076-m_acc_01' violates must_avoid color; Rank 3: item '1702e076-m_ftw_05' violates must_avoid color; Rank 3: item '1702e076-m_acc_01' violates must_avoid color

### `B0` — Case `r40` (rep)
- **Query:** Sáng mai đi cafe trời mát, tư vấn set đồ tránh mặc màu đen và không mặc quần jean.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Vi phạm Lớp A:** Rank 1: item '60ba1e12-f_acc_02' violates must_avoid color; Rank 2: item '60ba1e12-f_bot_06' violates must_avoid color; Rank 3: item '60ba1e12-f_top_04' violates must_avoid color; Rank 3: item '60ba1e12-f_bot_06' violates must_avoid color; Rank 3: item '60ba1e12-f_acc_02' violates must_avoid color

### `B0` — Case `r48` (rep)
- **Query:** Sáng mai đi dự lễ thành hôn của đồng nghiệp thân, trời lạnh 13 độ.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 missing required outerwear slot (got ['accessory', 'dress', 'footwear'])

### `B0` — Case `r56` (rep)
- **Query:** Tối nay đi tiệc trang trọng với công ty, trời mát, tránh mặc lại bộ hôm qua.
- **Status:** `ok` | **Error:** `None` | **Context used:** `none`
- **Chưa đạt assertion:** Top 1 avg formality 2.50 < min 3.0

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

### `B1` — Case `r48` (rep)
- **Query:** Sáng mai đi dự lễ thành hôn của đồng nghiệp thân, trời lạnh 13 độ.
- **Status:** `clarification` | **Error:** `None` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'clarification' (err=None)
- **Agent Trace:** `context(CLARIFICATION_REQUESTED)`

### `B1` — Case `r51` (rep)
- **Query:** Sáng mai đi làm văn phòng trời mát, cần mặc quần tây xanh navy.
- **Status:** `error` | **Error:** `NO_COMPLETE_OUTFIT` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'error' (err=NO_COMPLETE_OUTFIT)
- **Agent Trace:** `context(CONTEXT_EXTRACTED) -> wardrobe(CANDIDATE_POOL_BUILT)`

### `B1` — Case `r52` (rep)
- **Query:** Đi cafe chiều mai trời ấm áp, muốn mặc áo sơ mi trắng vải linen cho thoáng.
- **Status:** `error` | **Error:** `NO_COMPLETE_OUTFIT` | **Context used:** `rules`
- **Chưa đạt assertion:** Expected status='ok', got 'error' (err=NO_COMPLETE_OUTFIT)
- **Agent Trace:** `context(CONTEXT_EXTRACTED) -> wardrobe(CANDIDATE_POOL_BUILT)`

### `M-Full` — Case `r48` (rep)
- **Query:** Sáng mai đi dự lễ thành hôn của đồng nghiệp thân, trời lạnh 13 độ.
- **Status:** `ok` | **Error:** `None` | **Context used:** `gemini`
- **Chưa đạt assertion:** Top 1 missing required outerwear slot (got ['bottom', 'footwear', 'top'])
- **Agent Trace:** `context(CONTEXT_EXTRACTED) -> wardrobe(CANDIDATE_POOL_BUILT) -> fashion(EVALUATED_OUTFITS_PRODUCED) -> personalization(RANKED_OUTFITS_PRODUCED) -> coordinator(RECOMMENDATIONS_APPROVED)`

### `B2` — Case `r28` (rep)
- **Query:** Sáng mai đi làm văn phòng, trời mát, chọn đồ giúp mình.
- **Status:** `error` | **Error:** `PROVIDER_ERROR` | **Context used:** `none`
- **Chưa đạt assertion:** Expected status='ok', got 'error' (err=PROVIDER_ERROR)

### `B2` — Case `r47` (rep)
- **Query:** Tối mai rủ crush đi xem phim rồi ăn khuya, trời ấm áp, tư vấn bộ dễ thương gọn mắt.
- **Status:** `ok` | **Error:** `None` | **Context used:** `single_prompt_llm`
- **Vi phạm Lớp A:** Rank 3: explanation contains forbidden subjective claim

## 9. Giới Hạn Phương Pháp (Threats to Validity)

- Tủ đồ chuẩn (30 món nữ, 27 món nam) mô phỏng cấu trúc và tỷ lệ nhãn 'unknown' thực tế; khuyến nghị xuất thêm dữ liệu từ DB người dùng thực qua --export-wardrobe-from-db sau khi hoàn tất nạp 58 ảnh demo.
- Điểm chất lượng thời trang (Lớp B B2/B4) được chấm bởi LLM-as-a-Judge thay cho hội đồng chuyên gia dệt may chấm tay 100%; cần luôn kiểm tra cùng kết quả Calibration, Human-vs-Judge Spearman và Position Consistency.
- Quy mô mẫu 18 kịch bản (0 dev / 18 holdout) phù hợp kiểm chứng đồ án nhưng độ rộng khoảng tin cậy 95% (Wilson/Bootstrap CI) và mẫu số từng nhóm con vẫn cần được trình bày song song với tỷ lệ phần trăm.
