# Instructions for AI Coding Agents

## 1. Sources of Truth

Agents MUST read `docs/README.md` before implementation. When documents conflict, the following precedence order MUST apply:

1. `thesis/tro_ly_phoi_do_thong_minh_multi_agent.md`: thesis objectives and project scope.

2. `docs/01_product/PRD_MVP.md`: product requirements and acceptance criteria.

3. `docs/05_api/API_CONTRACT.md`: HTTP contract.

4. `docs/04_data/DATA_SCHEMA.md`: persistent data contract.

5. Relevant feature and architecture specifications.

6. The implementation roadmap and vibe-coding guide.

Agents MUST NOT add shopping, affiliate, social-network, or 3D body-scanning features to the MVP.

## 2. Session Memory

- Agents MUST read `CURRENT_STATE.md` at the start of every implementation session.

- Agents MUST update `CURRENT_STATE.md` after completing a task or changing the active task.

- `CURRENT_STATE.md` MUST contain the current phase, active task, most recently modified files, latest passing verification command, and next step.

- `CURRENT_STATE.md` is operational memory only. It MUST NOT override any source-of-truth specification.

## 3. Implementation Rules

- Work MUST follow the phases in `docs/07_implementation/MVP_ROADMAP.md`.

- Agents SHOULD read only the context files listed for the active phase.

- Documentation examples MUST NOT be copied mechanically. Implementation MUST match the installed library versions and the normative contracts.

- Every recommended item MUST belong to the active wardrobe of the requesting user.

- An LLM MUST NOT invent wardrobe items or select item identifiers.

- MVP feedback MUST use a 1–5 rating only. Like/Dislike controls MUST NOT be implemented.

- Rating prompts MUST follow `docs/06_features/PERSONALIZATION_AND_FEEDBACK_SPEC.md` and MUST NOT appear after every recommendation.

- Images MUST be accessed through the `ObjectStorage` abstraction. Business logic MUST NOT persist arbitrary local paths.

- Any schema or API change MUST update its source-of-truth document and associated tests in the same task.

- UI copy SHOULD be clear and concise. Decorative emoji SHOULD NOT be used. Functional icons MUST have accessible labels.

- UI and Frontend development MUST abide by `.agents/skills/taste-skill/SKILL.md`, `.agents/skills/redesign-skill/SKILL.md`, and `.agents/skills/soft-skill/SKILL.md`. Agents MUST avoid generic AI slop (no generic purple/blue gradients, no identical 3-column cards, no default system fonts like Arial). Agents MUST employ an Editorial / Warm Minimalist fashion aesthetic with refined typography hierarchy, thoughtful whitespace, and tactile micro-interactions.

## 4. Quality Requirements

- Backend code MUST target Python 3.11+, use type hints and Pydantic v2, and MUST NOT use mutable defaults.

- Frontend code MUST use TypeScript strict mode. `any` MUST NOT be used without an explicit justification.

- Unit tests MUST cover parsing, retrieval, scoring, grounding, and feedback cadence.

- Integration tests MUST cover the golden scenario.

- Secrets, user identifiers, and environment-specific URLs MUST NOT be hardcoded in source code.

## 5. Core Invariants

- **INVARIANT:** Cross-user wardrobe, outfit, rating, wear-log, and media access is forbidden.

- **INVARIANT:** A successful recommendation response contains only persisted outfit identifiers.

- **INVARIANT:** Every outfit item references an active wardrobe item owned by the same user at recommendation time.

- **INVARIANT:** An outfit uses either `top + bottom` or `dress`, never both branches together.

- **INVARIANT:** If generated try-on rendering fails but the moodboard fallback succeeds, the API returns success with `fallback_used=true`.

## 6. Commit and Pull Request Guidelines

- Use concise, imperative commit messages.

- Prefer `type(scope): summary` when practical, such as `feat(ocr): add licence scan validation` or `fix(dto): reject invalid booking dates`.

- Keep each commit focused on one coherent change.

- Commit messages MUST NOT contain roadmap phase labels such as `phase 1`, `phase 02`, or `phase xx`; phases are internal vibe-coding guidance and do not meaningfully describe a change.

- Pull requests SHOULD include the change summary, affected applications or services, test results, related issue, and any configuration or deployment notes.

- Include screenshots for visible UI changes.
 