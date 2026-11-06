# Multi-agent weather and intent audit — 2026-11-03

## Result and scope

Weather enrichment is integrated through the existing Context → Wardrobe → Fashion → Personalization → Coordinator graph. Open-Meteo was added and enabled locally; OpenWeather remains supported. The user explicitly authorized enabling Gemini Context using the existing Vision model (`gemini-3.6-flash`). Local configuration now selects both real services; secrets remain outside Git.

The deterministic pipeline passes the fixed context fixture and the controlled hot/cold/rain recommendation scenarios. Live weather succeeded for all three date/location requests in the final smoke run. **Gemini returned HTTP 429 for all five live attempts**, so their context was produced by the fallback parser. This does not establish live Gemini extraction accuracy.

## Reproduced issues and corrections

| Issue | Correction and evidence |
| --- | --- |
| Weather was disabled with no OpenWeather key configured | Added Open-Meteo city geocoding/hourly forecasts; keyless adapter is wired into dependency selection and enabled in local `.env`. |
| OpenWeather selected noon UTC regardless of event time | Select by city-local date and representative morning/afternoon/evening/night hour; adapters reject unavailable dates/times. |
| Provider spelling `Ðà Lạt` did not match Vietnamese `Đà Lạt` | Normalize both characters; direct real-geocoder reproduction plus regression test. |
| Work meetings, company attendance, teaching, and formal parties incorrectly triggered clarification | Ambiguity detection now consults the occasion parser. Frozen 30-query fixture labels were unchanged. |
| An LLM could replace recognized facts or claim API weather | Preserve recognized occasion/time/environment/date/location, explicit weather and temperature; only the weather adapter can produce API provenance. |
| An LLM could introduce unstated garment constraints | Keep provider constraints only when their phrase is present in the request; deterministic structured constraints remain authoritative. |
| Cooling clothing preferences could block weather enrichment | `ưu tiên đồ thoáng mát` is a clothing preference; it no longer creates a fabricated cool-weather observation. |
| Limited parsing of numeric dates/hours/temperature | Added ISO and day/month dates, `ngày kia`, hour-to-bucket mapping, numeric Celsius retention/classification. |
| Five aesthetic candidates could exclude the weather-suitable outfit | Shortlist by the same dynamic context weight profile with neutral personalization; retain context-independent aesthetic scores. Six prettier cold outfits no longer crowd out a hot-weather option. |
| Optional winter layers entered a rain outfit through weather relaxation | Optional outerwear/accessories cannot be added solely through weather relaxation; explicit requirements retain controlled warnings. |
| Stored styles did not match scoring-matrix aliases | Normalize athletic/street/business to sporty/streetwear/formal for style/clash scoring. |
| Item names fabricated functional capabilities | Use recorded functional flags. Water resistance implies rain suitability; rain suitability alone does not imply water resistance. |

## Does the pipeline follow the user's needs and fashion rules?

The tested sequence is:

1. Context interprets occasion, time/date, location, environment, explicit constraints and weather provenance. Ambiguous requests can ask for clarification.
2. Weather uses the requested city and date/time bucket only when the user did not already provide weather. Failure returns a warning and retains user/default data.
3. Wardrobe MUST retrieve only active, user-confirmed items owned by that user. Weather/formality relaxation is explicit; garment constraints are rechecked on complete outfits.
4. Fashion constructs `top + bottom + footwear` or `dress + footwear`, keeps valid branches, applies the documented color/style/proportion/formality/weather/function rules, and shortlists with context weights.
5. Personalization uses saved preferences, bounded fit signal, ratings/wear history and diversity. Coordinator validates ownership/completeness again and persists outfit IDs before success.

The governing scoring reference is [Fashion Knowledge Base](../03_domain/FASHION_KNOWLEDGE_BASE.md), including 40/35/25 aesthetic weights and the formal/comfort/active/balanced context vectors. Architecture text was aligned with that actual three-tier behavior; the old diagnostic weighted sum is not described as final selection. Rules are transparent product heuristics, not universal fashion judgments or guarantees of fabric performance. Search remains bounded (15 per category, 500 combinations, five shortlisted cores).

The hot/cold/rain integration tests use the real graph, HTTP weather adapter with controlled responses, real migrated temporary database, and owned garments. Top recommendations change to suitable garment groups; cold includes an appropriate jacket. Returned IDs are persisted, active and user-confirmed, and retries retain context/results.

## Verification

| Check | Result |
| --- | --- |
| Final full backend regression, excluding opt-in live tests | 664 passed, 32 deprecation warnings, 210.37 seconds |
| Fixed `context-v1`: 30 queries × five required fields | F1 0.88 before the ambiguity correction; 1.00 after; labels unchanged |
| Targeted weather/context/graph/F1 run | 27 passed; subsequent context/F1 targeted run 59 passed |
| Added Gemini HTTP success/malformed/429/timeout checks | Passed in 30 weather/graph tests; later alias/location regressions passed in 78 weather/fashion tests |
| Browser regression with isolated fake/offline providers | 9 passed, 51.1 seconds; Windows pipe-reset teardown diagnostics did not fail tests |
| Live smoke | Five requests through an isolated seeded wardrobe; all grounded, no graph errors; one clarification with zero outfits |
| Weather live success | 3/3 applicable requests; explicit 35°C retained as user weather; ambiguous query skipped lookup |
| Gemini live extraction | 0/5 successful; HTTP 429 on every attempt; explicit rules fallback |

Live run detail: [machine-readable evidence](WEATHER_CONTEXT_LIVE_2026-11-03.json). Its results were 26.2°C for Hà Nội cafe tonight, 23.0°C for Đà Lạt work tomorrow morning, and rainy 27.7°C for Hà Nội interview tomorrow. These are samples at execution time, not permanent weather claims. Limited seed data caused explicit relaxation warnings and low-scoring suggestions in some cases; no missing garments were invented. Recorded whole-graph sample times were 0.406–3.292 seconds; five samples with Gemini failures are not a p95 benchmark of successful Gemini operation.

F1 1.00 is limited to the deterministic parser's fixed 30-query fixture and five fields. It is not a general-language accuracy claim, a weather forecast accuracy measure, or a Gemini benchmark. Combined adverse conditions, exact event minutes, ambiguous foreign destinations, and subjective style quality need broader evaluation.

## Configuration and operation

Local configuration was updated without copying credentials into this document:

```dotenv
WEATHER_PROVIDER=openmeteo
WEATHER_TIMEOUT_SECONDS=5
CONTEXT_PROVIDER=gemini
LLM_MODEL=<model supported by your existing Gemini key>
```

`GEMINI_API_KEY` remains a local secret. This session reused the configured Vision model with the user's approval. Restart a running backend to reload provider settings. Until the HTTP 429 limit is resolved for that key/model, the application deliberately uses its rule-based fallback and returns a warning. No alternate key/model was substituted silently.

For OpenWeather instead, select `WEATHER_PROVIDER=openweather` and provide `WEATHER_API_KEY`. Normal backend tests and browser fixtures explicitly disable/mock remote providers, independently of local live settings.

Opt-in reproduction from `backend`:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_weather_context.py --live-weather --live-context --report ../docs/07_implementation/WEATHER_CONTEXT_LIVE_2026-11-03.json
```

Technical provider references and data attribution: [Open-Meteo forecast documentation](https://open-meteo.com/en/docs), [Open-Meteo geocoding documentation](https://open-meteo.com/en/docs/geocoding-api), [OpenWeather forecast documentation](https://openweathermap.org/api/forecast5), [Gemini GenerateContent reference](https://ai.google.dev/api/generate-content). Public Open-Meteo data attribution: Open-Meteo, CC BY 4.0.

No canonical database migration, reseeding, media rewrite, or frontend redesign was required. Pre-existing migration-0008/schema-test changes, generated `next-env.d.ts`, and the lecturer-plan draft remain outside this task commit.
