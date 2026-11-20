# Multi-Agent Fashion Stylist Documentation

## 1. Reading Order

| Order | Group | Purpose |
| :---: | :--- | :--- |
| 1 | `01_product` | Scope, user flows, and acceptance criteria |
| 2 | `02_architecture` | System architecture and agent responsibilities |
| 3 | `03_domain` | Fashion knowledge and scoring model, ingestion, and retrieval |
| 4 | `04_data` | Relational data and object storage |
| 5 | `05_api` | Frontend/backend HTTP contract |
| 6 | `06_features` | Personalization, feedback, and try-on behavior |
| 7 | `07_implementation` | Active roadmap, alignment backlog, test strategy, and vibe-coding prompts |
| — | `archive` | Historical records only; not a source of truth |

The Vietnamese thesis outline at `../thesis/tro_ly_phoi_do_thong_minh_multi_agent.md` is the academic scope authority. Root-level `AGENTS.md` defines how coding agents MUST use this documentation, and `CURRENT_STATE.md` records current execution state.

## 2. Documentation Tree

```text
AGENTS.md
CURRENT_STATE.md
thesis/
└── tro_ly_phoi_do_thong_minh_multi_agent.md

docs/
├── README.md
├── 01_product/
│   └── PRD_MVP.md
├── 02_architecture/
│   ├── SYSTEM_ARCHITECTURE.md
│   └── MULTI_AGENT_SPEC.md
├── 03_domain/
│   ├── FASHION_KNOWLEDGE_BASE.md        5-attribute profile, 3-tier scoring, dynamic weights
│   └── INGESTION_AND_RETRIEVAL_SPEC.md
├── 04_data/
│   ├── DATA_SCHEMA.md
│   └── OBJECT_STORAGE_SPEC.md
├── 05_api/
│   └── API_CONTRACT.md
├── 06_features/
│   ├── PERSONALIZATION_AND_FEEDBACK_SPEC.md
│   └── VIRTUAL_TRYON_SPEC.md
├── 07_implementation/
│   ├── ROADMAP.md                       active roadmap for upgrade work
│   ├── ALIGNMENT_BACKLOG.md             known divergences awaiting an owner decision
│   ├── TEST_STRATEGY.md
│   └── VIBE_CODING_GUIDE.md
└── archive/
    ├── README.md                        index of archived files
    ├── MVP_ROADMAP.md                   completed MVP Phases 1–7
    ├── KE_HOACH_TICH_HOP_GOP_Y_GIANG_VIEN.md   completed advisor-feedback plan
    └── reports/                         dated reviews, audits, spike and live-test reports
```

## 3. Documentation Rules

- A specification MUST define behavior, inputs/outputs, invariants, failure behavior, and acceptance criteria.
- JSON, tables, formulas, and short pseudocode MAY be used to clarify a contract.
- Complete Python or TypeScript implementations MUST live in source code and tests, not in design documents.
- Every concept MUST have one source of truth. Other documents SHOULD link to it instead of duplicating it.
- Decorative icons and emoji SHOULD NOT be used in headings or diagrams.
- Vietnamese MUST be retained only for user-query examples, test queries, and user-facing messages. Existing exceptions are tracked as D-1 in `07_implementation/ALIGNMENT_BACKLOG.md`.
- Dated reviews, audits, and evidence reports MUST be placed in `archive/reports/`. Normative folders `01`–`07` MUST contain only documents that describe current behavior or current plans.
- A divergence that cannot be fixed without an owner decision MUST be recorded in `07_implementation/ALIGNMENT_BACKLOG.md`.

## 4. Normative Decisions

- Orchestration MUST retain the five-node LangGraph workflow (`context`, `wardrobe`, `fashion`, `personalization`, `coordinator`) with bounded conditional feedback loops defined in `02_architecture/MULTI_AGENT_SPEC.md` (`fashion <-> wardrobe` targeted relaxation `<= 2` rounds and `coordinator critic -> fashion` critique reroute `<= 1` round). Open-ended or unbounded dynamic routing remains outside the current scope.
- Outfit ranking MUST follow the 3-tier model in `03_domain/FASHION_KNOWLEDGE_BASE.md` and MUST be deterministic. An LLM extracts context and writes explanations only.
- Feedback MUST use a 1–5 rating only and SHOULD be requested after every 5–10 eligible outfits, according to the cadence policy.
- Retrieval MUST use metadata filtering as the baseline. Full-text or semantic ranking is an optional measured enhancement.
- SQLite is the relational database. MinIO is the default image object store; a local-filesystem adapter MAY be used for tests or offline demonstrations.
- An upload MAY contain one item, multiple items, or a worn outfit. The system MUST classify the input and require user confirmation before persistence.
- Try-on output is an illustrative lookbook or a 2D virtual try-on image, with a moodboard fallback. These outputs MUST NOT claim body-fit accuracy.
