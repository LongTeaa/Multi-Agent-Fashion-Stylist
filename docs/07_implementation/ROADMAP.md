# Implementation Roadmap

This is the active roadmap. The completed MVP roadmap (Phases 1–7) is archived at `../archive/MVP_ROADMAP.md`, and the completed advisor-feedback integration plan at `../archive/KE_HOACH_TICH_HOP_GOP_Y_GIANG_VIEN.md`. Archived roadmaps MUST NOT be reopened; follow-up work MUST be added here as a new phase.

## 1. Status

| Field | Value |
| :--- | :--- |
| Baseline | MVP Phases 1–7 and advisor stages 1–6 complete; `main` at the merge of PR #11 |
| Active phase | None. The upgrade direction has not been approved yet. |
| Open alignment items | `ALIGNMENT_BACKLOG.md` |

Until a phase is approved, agents MUST NOT start feature work. Documentation alignment from `ALIGNMENT_BACKLOG.md` MAY proceed.

## 2. How to Add a Phase

Each phase MUST be a level-2 heading of the form `## Phase N — Title`, numbered from 1 within this roadmap, and MUST contain, in this order:

1. **Goal** — one or two sentences stating the user-visible or measurable outcome, and which thesis objective (chapter 1.2) it serves.
2. **Specification files** — the exact source-of-truth files and sections to read. A phase that changes the schema, API, or scoring MUST list the document it will update.
3. **Checklist** — bounded tasks as `- [ ]` items. A task MAY be checked only after its verification passes.
4. **Acceptance criteria** — observable conditions, including the golden scenario when recommendation behavior changes.
5. An executable-command block: a bold line reading `Executable Command:` or `Executable Commands:` followed by a fenced `powershell` block run from the repository root. Default verification MUST NOT require external API credentials.

`scripts/verify_documentation.ps1` checks that every phase heading has an executable-command block.

## 3. Phases

No phase is defined yet.

## 4. Roadmap Invariants

- **INVARIANT:** A phase is complete only when every checklist item is complete and every listed command passes.
- **INVARIANT:** A later phase MUST NOT be used to hide a failure in an earlier phase.
- **INVARIANT:** `CURRENT_STATE.md` reflects the actual active phase and latest passing command.
- **INVARIANT:** External API credentials are not required for default phase verification.
- **INVARIANT:** A phase MUST NOT add shopping, affiliate, social-network, or 3D body-scanning features unless the thesis scope is changed first.
