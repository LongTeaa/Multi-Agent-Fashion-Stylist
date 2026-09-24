# Vibe Coding Guide

## 1. Session Discipline

Every session MUST begin by reading `AGENTS.md`, `CURRENT_STATE.md`, and `docs/README.md`. Work SHOULD be limited to one roadmap task with one explicit verification target. A coding agent MUST inspect the workspace before creating or replacing files.

Design documents intentionally omit complete Python and TypeScript implementations. Specifications define contracts; source code and automated tests demonstrate compliance.

## 2. Required Session-Start Prompt Formula

The startup prompt MUST follow this order:

1. **Context Anchor** — repository, current phase/state, and governing rules.
2. **Spec Files** — exact source-of-truth files for the task.
3. **Specific Task** — one bounded implementation outcome.
4. **Verification Command** — an exact executable command from the roadmap.

Template:

```text
Context Anchor:
Work in the Multi-Agent-Fashion-Stylist repository. Read AGENTS.md,
CURRENT_STATE.md, docs/README.md, and Phase [N] in
docs/07_implementation/MVP_ROADMAP.md. Preserve all documented INVARIANTS.

Spec Files:
- [exact/spec/path.md, section]
- [exact/spec/path.md, section]
- docs/07_implementation/TEST_STRATEGY.md, Phase [N]

Specific Task:
Implement only [one concrete task]. First inspect the existing code and tests.
Do not implement adjacent roadmap tasks. Update CURRENT_STATE.md after verification.

Verification Command:
[paste the exact command from MVP_ROADMAP.md]
```

## 3. Examples

### 3.1 API Task

```text
Context Anchor:
Read AGENTS.md, CURRENT_STATE.md, docs/README.md, and Phase 2 of the roadmap.

Spec Files:
- docs/05_api/API_CONTRACT.md, Ingestion API
- docs/03_domain/INGESTION_AND_RETRIEVAL_SPEC.md
- docs/07_implementation/TEST_STRATEGY.md, Phase 2

Specific Task:
Implement only POST /api/v1/ingestions with typed schemas, upload validation,
private ObjectStorage persistence, normalized errors, and its target tests.

Verification Command:
pytest backend/tests/unit/test_upload_validation.py backend/tests/integration/test_ingestion_flow.py -q
```

### 3.2 Agent Task

```text
Context Anchor:
Read AGENTS.md, CURRENT_STATE.md, docs/README.md, and Phase 4 of the roadmap.

Spec Files:
- docs/02_architecture/MULTI_AGENT_SPEC.md, Context Agent
- docs/03_domain/INGESTION_AND_RETRIEVAL_SPEC.md, Search-Intent Extraction
- docs/07_implementation/TEST_STRATEGY.md, Phase 4

Specific Task:
Implement only the Context Agent and its fallback parser. Preserve Vietnamese
test queries and do not implement the Wardrobe Agent in this task.

Verification Command:
pytest backend/tests/unit/test_context_agent.py -q
```

## 4. Narrow Follow-Up Prompts

### Contract Implementation

```text
Implement [METHOD PATH] exactly as specified in docs/05_api/API_CONTRACT.md.
Use the resolved X-User-Id for ownership, typed request/response schemas, and the
standard error envelope. Add contract and integration assertions. Do not add
response fields that are absent from the contract.
```

### Specification Drift Repair

```text
Stop new feature work. Compare the implementation with [spec path and section].
Identify the drift, apply the smallest compliant fix, add a regression test, run
the relevant roadmap verification command, and update CURRENT_STATE.md only if it passes.
```

## 5. Prompts to Avoid

- `Implement the entire application from the docs.`
- `Choose any model or technology you think is best.` when architecture already defines an abstraction.
- `Make the UI beautiful.` without measurable acceptance criteria.
- `Use AI to select an outfit.` without grounding and deterministic scoring constraints.

Overly broad prompts increase schema duplication, bypass invariants, and make phase ownership ambiguous.

## 6. Definition of Done for One Task

- Implementation matches the highest-priority applicable source of truth.
- New and related tests pass with the exact verification command.
- No secret, fixed user ID, or environment-specific URL is hardcoded.
- API/OpenAPI or UI states are checked when affected.
- The roadmap checkbox is updated only after verification passes.
- `CURRENT_STATE.md` records the phase, completed task, modified files, passing command, and next step.

## 7. Missing Decisions

An agent MUST NOT invent a material product decision. If a missing choice changes persistent data, API behavior, privacy, or MVP scope, the agent MUST record it under an `Open Decisions` section in the relevant specification or ask the user before implementation.
