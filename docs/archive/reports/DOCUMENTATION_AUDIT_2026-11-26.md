# Đối chiếu tài liệu đặc tả với mã nguồn — 2026-11-26

Thực hiện trên `main` tại `fb829d6`, trước khi viết báo cáo khóa luận. Mục đích: xác định tài liệu nào trong `docs/01`–`07` có thể dùng làm nguồn cho báo cáo. `scripts/verify_documentation.ps1` chỉ kiểm tra cấu trúc thư mục, nên nội dung được đối chiếu thủ công với code. Schema và route được so bằng script đọc model SQLModel và route FastAPI; số liệu truy xuất lấy từ `backend/tests/evaluation/test_retrieval_metrics.py`.

## 1. Phần khớp với code

| Tài liệu | Đã kiểm tra |
| :--- | :--- |
| `MULTI_AGENT_SPEC.md` | 5 node và các cạnh có điều kiện (`stylist_graph.py`); nới lỏng tối đa 2 vòng; phản biện 1 vòng, giữ phương án cũ khi điểm giảm quá 0,05; 500 tổ hợp, giữ 50 ứng viên, 15 món mỗi nhóm; đa dạng 0,08 / 0,10; ngưỡng ghi chú 0,65; trường `StylistContext` |
| `FASHION_KNOWLEDGE_BASE.md` | 4 hồ sơ trọng số; ma trận phom dáng 5×5 và các hằng số điều chỉnh; ma trận phong cách; các mức điểm màu; phạt 0,40 / 0,15 (tối đa 0,30) / 0,10 |
| `PERSONALIZATION_AND_FEEDBACK_SPEC.md` | 0,35 / 0,25 / 0,20 / 0,20; quy đổi sao; EMA α = 0,30, kẹp [-1, 1]; cần ít nhất 5 rating; ngưỡng hỏi 5–10; thời gian chờ sau khi bỏ qua |
| `DATA_SCHEMA.md` | 17 bảng; mọi cột đều được mô tả, trừ các cột bổ sung ở mục 2 |
| `API_CONTRACT.md` | Mọi endpoint nghiệp vụ; mọi trường của phản hồi chat |
| `OBJECT_STORAGE_SPEC.md` | Quy ước object key |
| `INGESTION_AND_RETRIEVAL_SPEC.md` | Trọng số truy xuất 0,30 / 0,25 / 0,25 / 0,20; trộn full-text 0,8 / 0,2 |

## 2. Sai lệch đã sửa trong lần này

| # | Tài liệu | Sai lệch | Đã sửa thành |
| :---: | :--- | :--- | :--- |
| 1 | `VIRTUAL_TRYON_SPEC.md` §3, §7; `API_CONTRACT.md` §8.1–8.2; `PRD_MVP.md` §4.4, US-10, §7 | Mô tả chế độ thử đồ bất đồng bộ (HTTP 202, trạng thái `processing`, tác vụ nền). Code chỉ có đường đồng bộ | Đường đồng bộ; xóa 202 và ví dụ `processing` |
| 2 | `SYSTEM_ARCHITECTURE.md` §3, §7 | Thiếu provider `flux` (mặc định từ 2026-11-22), `FAL_KEY`, `FLUX_VTO_MODEL`, `DETECTOR_FALLBACK_BACKEND`, `GEMINI_KEY_COOLDOWN_SECONDS` | Bổ sung |
| 3 | `INGESTION_AND_RETRIEVAL_SPEC.md` §7 | Precision@5 ghi 0,845 / 0,8783; giá trị hiện tại 0,79 / 0,8233 từ 2026-11-18 | Cập nhật và ghi lý do thay đổi |
| 4 | `SYSTEM_ARCHITECTURE.md` §5, §6, §9 | Invariant "agent không vượt repository"; thực tế không có repository cho DB, Wardrobe/Personalization/Coordinator đọc qua `Session` được truyền vào. Mục §5 chỉ nói MinIO | Mô tả đúng phân lớp; invariant mới: agent chỉ dùng `Session` được truyền vào, chỉ Coordinator ghi |
| 5 | `MULTI_AGENT_SPEC.md` §8 | Try-On Agent chỉ có timeout 8 giây; thực tế 8 giây cho lookbook, 90 giây (`TRYON_TIMEOUT_SECONDS`) cho mỗi lần gọi try-on; Try-On Agent là service | Ghi cả hai mức timeout và vị trí service |
| 6 | `FASHION_KNOWLEDGE_BASE.md` §3.2 | Quy tắc màu ghi "quá 3 họ màu"; code là "từ 3 họ trở lên không có neo trung tính"; thiếu mức 0,55 và phạt 0,20 mỗi màu vượt quá 3 | Bổ sung đúng theo `fashion_scoring.py` |
| 7 | `FASHION_KNOWLEDGE_BASE.md` §5 | "Circuit Breaker" không tồn tại | Mô tả cơ chế thật: một lần gọi có giới hạn thời gian, fallback luật, khóa Gemini tạm ngưng khi gặp 429 |
| 8 | `API_CONTRACT.md` §8.3, §9, §10 | Ví dụ avatar sai tên trường (`gender`), URL (`.webp`), thiếu `created_at`; thiếu `/tryons/presets/{preset_gender}`, `/system/cleanup-metrics`, `/health`; thiếu 4 mã lỗi nghiệp vụ và 5 mã của handler chung | Sửa ví dụ, thêm mục 9.2 và các mã lỗi |
| 9 | `DATA_SCHEMA.md` §3.15, §3.17 | `render_mode` ghi `vton_personal`/`vton_preset`, code ghi `virtual_tryon`; thiếu `tryon_avatars.name`, `preset_gender` | Sửa theo code |
| 10 | `OBJECT_STORAGE_SPEC.md` §3 | Giữ object 30 ngày sau khi xóa mềm, nhưng không có job xóa vật lý | Ghi rõ hiện trạng |

## 3. Chưa sửa, cần lưu ý khi viết báo cáo

- **A-1** (`ALIGNMENT_BACKLOG.md`): `DELETE /tryons/avatars/{avatar_id}` trả `200` có body, hợp đồng ghi `204`. Vẫn chờ chủ dự án quyết định.
- **Kịch bản B** trong `FASHION_KNOWLEDGE_BASE.md` §4 mô tả lời giải thích "phân tích độ thông thoáng của sợi vải", trái với quy tắc giải thích ở `MULTI_AGENT_SPEC.md` §7. Không dùng đoạn này làm ví dụ đầu ra; lấy ví dụ từ ứng dụng đang chạy.
- **Độ trễ:** mục tiêu p95 ≤ 5 giây (`PRD_MVP.md` §7) đạt khi tắt giải thích LLM (4,2 giây) và không đạt khi bật (8,7 giây) theo `LIVE_CHAT_LATENCY_2026-11-25.md`.
- **Báo cáo trong `docs/archive/`** là ảnh chụp tại thời điểm chạy. Ví dụ `LIVE_INGESTION_EVALUATION_2026-11-25.md` §4 ghi detector mặc định là YOLO-World, nhưng Phase 5 cùng ngày đổi sang Gemini với YOLO-World dự phòng. Khi trích dẫn, ghi cấu hình của lần chạy.
- Đề cương `thesis/tro_ly_phoi_do_thong_minh_multi_agent.md` chỉ phản ánh bản MVP; báo cáo dựa trên mẫu của khoa và các tài liệu trong `docs/`.
