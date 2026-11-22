# Documentation Archive

Everything in this directory is a historical record. It MUST NOT be used as a source of truth: current behavior is defined by the documents listed in `../README.md`. Archived files are kept unchanged except for link repairs required by the move, so commands, file paths, and statuses inside them describe the repository at the time they were written.

New dated reviews, audits, spike reports, and live-test reports SHOULD be added to `reports/` with a `_YYYY-MM-DD` suffix.

## Completed Plans

| File | Content | Status |
| :--- | :--- | :--- |
| `MVP_ROADMAP.md` | MVP Phases 1–7 with their verification commands | Complete |
| `KE_HOACH_TICH_HOP_GOP_Y_GIANG_VIEN.md` | Advisor-feedback integration plan: 5-attribute garment profile, 3-tier scoring, dynamic weights (Vietnamese) | Complete |

## Reports

| File | Date | Content |
| :--- | :--- | :--- |
| `reports/ADVERSARIAL_AUDIT_2026-09-17.md` | 2026-09-17 | Adversarial audit with a BLOCKED verdict (5 critical, 15 major findings). Its findings were not re-verified one by one when archived; later reviews describe the subsequent state (Vietnamese) |
| `reports/LIVE_TEST_ISSUES_2026-09-20.md` | 2026-09-20 | Issues found while testing with live providers (Vietnamese) |
| `reports/PROJECT_REVIEW_2026-11-02.md` | 2026-11-02 | Repository review: 3 P1 and 9 P2 findings |
| `reports/UX_REVIEW_AND_REMEDIATION_2026-11-02.md` | 2026-11-02 | UX observations and remediation proposal |
| `reports/REAL_IMAGE_INGESTION_REVIEW_2026-11-02.md` | 2026-11-02 | Real-photo ingestion and Gemini box-coordinate review |
| `reports/CROP_BOUNDARY_AND_ANNOTATION_REVIEW_2026-11-03.md` | 2026-11-03 | Crop boundary corpus and annotation v2 |
| `reports/MULTI_AGENT_WEATHER_AUDIT_2026-11-03.md` | 2026-11-03 | Weather/context integration audit and live acceptance evidence |
| `reports/MAIN_RECONCILIATION_2026-11-03.md` | 2026-11-03 | Reconciliation of local and remote `main` |
| `reports/REVIEW_CLOSURE_2026-11-03.md` | 2026-11-03 | Closure of the 2026-11-02 review and UX findings |
| `reports/PR_7_REVIEW_2026-11-05.md` | 2026-11-05 | Review of PR #7 (wardrobe ingestion optimization) |
| `reports/FASHN_VTON_SPIKE_REPORT.md` | 2026-11-06 | FASHN VTON v1.5 feasibility spike (Vietnamese) |
| `reports/PROJECT_REVIEW_2026-11-18.md` | 2026-11-18 | Whole-project review: multi-agent depth, data, ingestion, try-on options, benchmark plan (Vietnamese) |
| `reports/TRYON_PROVIDER_SPIKE_2026-11-22.md` | 2026-11-22 | FASHN Try-On v1.6 vs FLUX VTO on ten demo outfits: latency, cost, blind ratings; decision to switch to FLUX VTO |

Machine-readable evidence (`reports/*.json`) and screenshots (`reports/screenshots/`) belong to the reports that link to them.
