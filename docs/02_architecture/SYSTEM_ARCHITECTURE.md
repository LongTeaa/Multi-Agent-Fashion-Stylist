# System Architecture Specification — MVP

## 1. Architecture Decision

The application is a monorepo containing a Next.js frontend, a FastAPI backend, a five-node LangGraph workflow with bounded feedback loops, SQLite, and private object storage. External AI and weather providers MUST be accessed through service interfaces so that implementations can be replaced and tested independently.

Orchestration MUST keep the five-node graph defined in `MULTI_AGENT_SPEC.md` (`context`, `wardrobe`, `fashion`, `personalization`, `coordinator`) with bounded conditional feedback edges (`fashion <-> wardrobe` targeted relaxation up to 2 rounds and `coordinator critic -> fashion` critique reroute up to 1 round). The Coordinator validates grounding, executes final persistence once, and synthesizes the response; open-ended or unbounded dynamic routing remains outside scope.

## 2. Components

```text
Next.js Web Client
    |
FastAPI REST API
    |-- Wardrobe ingestion service -- Detector + Vision provider
    |-- Context/weather service ----- Context (LLM) + Weather provider
    |-- Stylist LangGraph workflow
    |-- Try-on service -------------- Try-on (VTON) provider, Image provider, moodboard
    |-- ObjectStorage --------------- MinIO / local adapter
    |-- SQLModel -------------------- SQLite
```

ChromaDB MUST NOT be a default MVP dependency. A semantic index MAY be introduced only when the retrieval benchmark in `../03_domain/INGESTION_AND_RETRIEVAL_SPEC.md` demonstrates a measurable need.

## 3. Technology Stack

| Component | Normative choice |
| :--- | :--- |
| Frontend | Next.js App Router, TypeScript strict mode, Tailwind CSS |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLModel |
| Workflow | LangGraph five-node state graph with bounded feedback loops (`MULTI_AGENT_SPEC.md`) |
| Relational database | SQLite for development/MVP; migration path to PostgreSQL |
| Object storage | MinIO; local-filesystem adapter for tests/offline demonstrations |
| Item detection | `DETECTOR_BACKEND`: `auto` (follows `VISION_PROVIDER`), `fake`, `gemini`, or `yolo_world` (local ONNX model) |
| Vision and LLM | Provider abstraction (`fake` or `gemini`; context also `fallback` rules); model identifiers and an optional Vision fallback model from environment settings; multiple Gemini keys MAY be rotated |
| Image generation | Provider abstraction (`disabled`, `fake`, `gemini`) with a dedicated image model from environment settings |
| 2D virtual try-on | Provider abstraction (`disabled`, `fake`, `fashn`); FASHN VTON through a configurable Hugging Face Space |
| Weather | Open-Meteo or OpenWeather, or `disabled`, with a deterministic fallback |

Preview model identifiers MUST NOT be hardcoded in business logic. Model identifiers MUST be configurable to avoid coupling implementation to a short-lived provider version.

## 4. Primary Data Flows

### 4.1 Wardrobe Ingestion

`upload -> validate -> detect/crop -> analyze -> user confirmation -> database + object storage -> retrieval document`

### 4.2 Recommendation

`context -> wardrobe retrieval <-> fashion scoring (bounded relaxation <= 2) -> personalization -> coordinator critic (-> fashion reroute <= 1) -> persistence -> response`

### 4.3 Try-On

Try-on is a separate on-demand API operation that accepts a persisted `outfit_id`. It MUST NOT block the recommendation pipeline.

## 5. Data Boundaries

- SQLite MUST store entities, relationships, ratings, and wear history.
- MinIO MUST store original uploads, item crops, thumbnails, generated lookbooks, and moodboards.
- The API MUST NOT expose raw object keys. It MUST return a short-lived signed URL or an authenticated media-proxy URL.
- LLM calls SHOULD receive only the minimum data required for the active operation.
- Every database and object-storage operation MUST be scoped to `user_id`.

## 6. Target Source Tree

```text
frontend/
  src/app/{chat,wardrobe,profile,saved}/
  src/components/
  src/hooks/
  src/lib/
  src/types/
backend/
  app/api/
  app/agents/
  app/core/
  app/models/
  app/schemas/
  app/services/
  app/repositories/
  tests/{unit,contract,integration,e2e}/
  scripts/
data/fixtures/
docs/
thesis/
```

`services` integrate external providers. `repositories` own database and storage access. Agents MUST receive dependencies explicitly and MUST NOT create arbitrary database or provider clients.

## 7. Environment Contract

The complete, placeholder-only variable list is `.env.example` at the repository root, validated by `backend/app/core/config.py`. Variables fall into these groups:

| Group | Examples |
| :--- | :--- |
| Application | `DATABASE_URL`, `FRONTEND_URL` |
| Provider selection | `VISION_PROVIDER`, `DETECTOR_BACKEND`, `CONTEXT_PROVIDER`, `ENABLE_LLM_EXPLANATIONS`, `WEATHER_PROVIDER`, `IMAGE_PROVIDER`, `TRYON_PROVIDER` |
| Model identifiers | `LLM_MODEL`, `VISION_MODEL`, `VISION_FALLBACK_MODEL`, `DETECTOR_MODEL`, `IMAGE_MODEL`, `YOLO_WORLD_MODEL_PATH`, `FASHN_TRYON_SPACE` |
| Timeouts and limits | `*_TIMEOUT_SECONDS`, `INGESTION_MAX_CONCURRENCY` |
| Credentials | `GEMINI_API_KEY`, `GEMINI_API_KEYS`, `WEATHER_API_KEY`, `HF_TOKEN` |
| Object storage | `OBJECT_STORAGE_BACKEND`, `MINIO_*`, `SIGNED_URL_TTL_SECONDS` |

Defaults MUST keep every external provider fake or disabled, so that a fresh checkout runs without credentials.

The complete object-storage contract is defined in `../04_data/OBJECT_STORAGE_SPEC.md`.

## 8. Reliability Behavior

| Failure | Required behavior |
| :--- | :--- |
| LLM context extraction fails | Use the rule-based fallback; request clarification if required fields remain ambiguous |
| Weather provider fails | Preserve weather explicitly supplied by the user; otherwise use a documented default and warning |
| Vision provider fails | Preserve the ingestion batch and allow manual metadata entry/correction |
| Image generation fails or exceeds 8 seconds | Generate a moodboard; return HTTP 200 when fallback succeeds |
| 2D try-on provider fails, times out, or exhausts quota | Follow the fallback rules in `../06_features/VIRTUAL_TRYON_SPEC.md`; a successful moodboard fallback reports `fallback_used=true` |
| Object storage fails | MUST NOT commit a database record that references a missing object |
| Grounding validation fails | MUST NOT persist recommendations; return a normalized safe error |

## 9. Architecture Invariants

- **INVARIANT:** Provider-specific SDK objects do not cross service boundaries.
- **INVARIANT:** Agents do not bypass repositories to access persistence.
- **INVARIANT:** Heavy try-on work is isolated from the recommendation request.
- **INVARIANT:** Storage and database ownership checks use the same authenticated user identity.
