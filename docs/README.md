# Multi-Agent Fashion Stylist Documentation

## 1. Reading Order

| Order | Group | Purpose |
| :---: | :--- | :--- |
| 1 | `01_product` | Scope, user flows, and acceptance criteria |
| 2 | `02_architecture` | System architecture and agent responsibilities |
| 3 | `03_domain` | Fashion rules, ingestion, and retrieval |
| 4 | `04_data` | Relational data and object storage |
| 5 | `05_api` | Frontend/backend HTTP contract |
| 6 | `06_features` | Personalization, feedback, and try-on behavior |
| 7 | `07_implementation` | Roadmap, test strategy, and vibe-coding prompts |

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
│   ├── FASHION_KNOWLEDGE_BASE.md
│   └── INGESTION_AND_RETRIEVAL_SPEC.md
├── 04_data/
│   ├── DATA_SCHEMA.md
│   └── OBJECT_STORAGE_SPEC.md
├── 05_api/
│   └── API_CONTRACT.md
├── 06_features/
│   ├── PERSONALIZATION_AND_FEEDBACK_SPEC.md
│   └── VIRTUAL_TRYON_SPEC.md
└── 07_implementation/
    ├── MVP_ROADMAP.md
    ├── TEST_STRATEGY.md
    └── VIBE_CODING_GUIDE.md
```

## 3. Documentation Rules

- A specification MUST define behavior, inputs/outputs, invariants, failure behavior, and acceptance criteria.
- JSON, tables, formulas, and short pseudocode MAY be used to clarify a contract.
- Complete Python or TypeScript implementations MUST live in source code and tests, not in design documents.
- Every concept MUST have one source of truth. Other documents SHOULD link to it instead of duplicating it.
- Decorative icons and emoji SHOULD NOT be used in headings or diagrams.
- Vietnamese MUST be retained only for user-query examples, test queries, and user-facing messages.

## 4. Normative MVP Decisions

- Orchestration MUST use a fixed pipeline. The Coordinator validates grounding and synthesizes the result; dynamic routing is outside MVP scope.
- Feedback MUST use a 1–5 rating only and SHOULD be requested after every 5–10 eligible outfits, according to the cadence policy.
- Retrieval MUST use metadata filtering as the baseline. Full-text or semantic ranking is an optional measured enhancement.
- SQLite is the MVP relational database. MinIO is the default image object store; a local-filesystem adapter MAY be used for tests or offline demonstrations.
- An upload MAY contain one item, multiple items, or a worn outfit. The system MUST classify the input and require user confirmation before persistence.
- MVP try-on output is an illustrative, reference-conditioned lookbook. The fallback is a moodboard and MUST NOT claim body-fit accuracy.
