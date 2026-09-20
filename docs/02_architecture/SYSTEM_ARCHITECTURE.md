# System Architecture Specification — MVP

## 1. Architecture Decision

The application is a monorepo containing a Next.js frontend, a FastAPI backend, a fixed LangGraph workflow, SQLite, and private object storage. External AI and weather providers MUST be accessed through service interfaces so that implementations can be replaced and tested independently.

The MVP MUST use a fixed pipeline. The Coordinator executes validation, persistence, and response synthesis at the end of the workflow; it is not a dynamic router. Dynamic routing is outside MVP scope.

## 2. Components

```text
Next.js Web Client
    |
FastAPI REST API
    |-- Wardrobe ingestion service -- Vision provider
    |-- Context/weather service ----- Weather provider
    |-- Stylist LangGraph workflow
    |-- Try-on service -------------- Image provider
    |-- ObjectStorage --------------- MinIO / local adapter
    |-- SQLModel -------------------- SQLite
```

ChromaDB MUST NOT be a default MVP dependency. A semantic index MAY be introduced only when the retrieval benchmark in `../03_domain/INGESTION_AND_RETRIEVAL_SPEC.md` demonstrates a measurable need.

## 3. Technology Stack

| Component | Normative choice |
| :--- | :--- |
| Frontend | Next.js App Router, TypeScript strict mode, Tailwind CSS |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLModel |
| Workflow | LangGraph fixed state graph |
| Relational database | SQLite for development/MVP; migration path to PostgreSQL |
| Object storage | MinIO; local-filesystem adapter for tests/offline demonstrations |
| Vision and LLM | Provider abstraction; model identifiers from environment settings |
| Image generation | Provider abstraction; a dedicated image model from environment settings |
| Weather | OpenWeatherMap or an equivalent provider with a deterministic fallback |

Preview model identifiers MUST NOT be hardcoded in business logic. Model identifiers MUST be configurable to avoid coupling implementation to a short-lived provider version.

## 4. Primary Data Flows

### 4.1 Wardrobe Ingestion

`upload -> validate -> detect/crop -> analyze -> user confirmation -> database + object storage -> retrieval document`

### 4.2 Recommendation

`context -> wardrobe retrieval -> fashion scoring -> personalization -> coordinator -> persistence -> response`

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

```env
DATABASE_URL=sqlite:///./data/fashion_stylist.db
FRONTEND_URL=http://localhost:3000
LLM_MODEL=provider_model_name
VISION_MODEL=provider_model_name
IMAGE_MODEL=provider_image_model_name
GEMINI_API_KEY=your_api_key
WEATHER_API_KEY=your_weather_api_key
OBJECT_STORAGE_BACKEND=minio
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key
```

The complete object-storage contract is defined in `../04_data/OBJECT_STORAGE_SPEC.md`.

## 8. Reliability Behavior

| Failure | Required behavior |
| :--- | :--- |
| LLM context extraction fails | Use the rule-based fallback; request clarification if required fields remain ambiguous |
| Weather provider fails | Preserve weather explicitly supplied by the user; otherwise use a documented default and warning |
| Vision provider fails | Preserve the ingestion batch and allow manual metadata entry/correction |
| Image generation fails or exceeds 8 seconds | Generate a moodboard; return HTTP 200 when fallback succeeds |
| Object storage fails | MUST NOT commit a database record that references a missing object |
| Grounding validation fails | MUST NOT persist recommendations; return a normalized safe error |

## 9. Architecture Invariants

- **INVARIANT:** Provider-specific SDK objects do not cross service boundaries.
- **INVARIANT:** Agents do not bypass repositories to access persistence.
- **INVARIANT:** Heavy try-on work is isolated from the recommendation request.
- **INVARIANT:** Storage and database ownership checks use the same authenticated user identity.
