# Báo Cáo Đối Chiếu Người Chấm Mù vs LLM Judge

- **Số người chấm mù độc lập (ẩn danh):** `3` (R1, R2, R3)
- **Số mẫu hiệu chuẩn:** `20`
- **Độ đồng thuận liên người chấm (Pairwise Spearman rho TB):** `0.9463`
- **Sai số tuyệt đối trung bình giữa người chấm (Inter-Rater MAE):** `0.6333`
- **LLM Judge:** `openai/gpt-6.1-terra` (`openai_compatible`)
- **Human vs Judge Spearman rho (thực tế):** `0.8953`
- **Human vs Judge MAE:** `0.4389`

| Sample ID | Nhãn | TB Người chấm (1-5) | Điểm LLM Judge | Chênh lệch |
| :--- | :---: | :---: | :---: | :---: |
| `cal_bad_01` | `bad` | 1.44 | 2.00 | 0.56 |
| `cal_bad_02` | `bad` | 1.89 | 2.00 | 0.11 |
| `cal_bad_03` | `bad` | 1.22 | 2.67 | 1.44 |
| `cal_bad_04` | `bad` | 3.11 | 2.00 | 1.11 |
| `cal_bad_05` | `bad` | 1.22 | 2.00 | 0.78 |
| `cal_bad_06` | `bad` | 1.78 | 2.17 | 0.39 |
| `cal_bad_07` | `bad` | 1.22 | 2.00 | 0.78 |
| `cal_bad_08` | `bad` | 2.89 | 3.17 | 0.28 |
| `cal_good_01` | `good` | 4.89 | 4.83 | 0.06 |
| `cal_good_02` | `good` | 4.67 | 4.83 | 0.17 |
| `cal_good_03` | `good` | 4.78 | 4.17 | 0.61 |
| `cal_good_04` | `good` | 3.56 | 4.17 | 0.61 |
| `cal_good_05` | `good` | 4.56 | 4.67 | 0.11 |
| `cal_good_06` | `good` | 4.56 | 4.00 | 0.56 |
| `cal_good_07` | `good` | 4.67 | 4.67 | 0.00 |
| `cal_good_08` | `good` | 4.22 | 4.67 | 0.44 |
| `cal_mid_01` | `mediocre` | 3.44 | 3.50 | 0.06 |
| `cal_mid_02` | `mediocre` | 3.33 | 3.50 | 0.17 |
| `cal_mid_03` | `mediocre` | 3.67 | 3.83 | 0.17 |
| `cal_mid_04` | `mediocre` | 2.89 | 2.50 | 0.39 |
