# W1 Notion Task Audit — Template + Update Record

Audit of the 11 `🔨 Build`-category W1 pages in the Notion "All task" database against what W1 actually shipped, per `docs/progress/task_summaries.md` (goal/files ground truth) and `w1_review_pre_w2_plan.md` (removed; see git history) (the F-01…F-14 findings and T-1…T-6 fixes from the pre-W2 hardening pass, PR #13). Scope is the Build pages only — the separate "W1 Q: …" interview-prep pages are a different kind of content and are not covered here.

Before this audit, 7 of the 11 pages were completely blank despite being marked "Done," and the 4 with content used three different ad-hoc formats with no explicit Goal line. Two tasks (structured-output validation, retries/idempotency) had a documented post-hoc defect from the W1 review that wasn't reflected in Notion at all.

## Standard W1 task-page template

```
**Goal:** <one sentence — the concrete problem this task solves, in plain language>

<1–4 bullets: what was actually built — file/module names only where they aid recall>

**Reference:** <ADR number(s) and/or commit, if any — omit if none>

**Correction (pre-W2 hardening, 2026-09-27):** <only if the W1 review found and fixed a defect in this task's original work — link the finding (F-0x) and what changed>

**Follow-up:** <only if something was deliberately deferred to W2+ — omit otherwise>
```

Rules: Goal is always present, one sentence, solved-a-problem framing (not a restatement of the title). Bullets stay short — this is a Notion recall aid, not a duplicate of `ombuds_build_task_summaries.md`. Omit a labeled field entirely rather than writing "None."

## Per-task record

1. **Design the folder structure to the project** — was blank. Goal: establish the feature-sliced `src/ombuds/` layout per ADR-0002 before any real code lands.
2. **Implement EU261 rules engine + unit tests** — had unstructured content; reformatted into template, Goal per the deterministic-calculator framing, ADR-0004 referenced.
3. **Call OpenAI & Anthropic APIs directly, compare outputs** — had rich content but no Goal line; Goal added, existing detail kept as bullets.
4. **Stub approval_gate as deny-all** — had unstructured content; reformatted, Goal + ADR-0004 + Follow-up (replaced by real gate in W2).
5. **Define tool schemas (check_eligibility, log_claim) + parse tool-use loop** — was blank. Goal added; Follow-up notes `issue_payment` schema deferred to W2.
6. **Build FastAPI /triage endpoint** — was blank. Goal added, explicitly distinguishing this raw-SDK loop from the later LangGraph agent.
7. **Write unit tests for tool-calling parser + endpoint** — was blank. Goal added (closing happy-path-only gaps).
8. **Implement streaming (SSE) + buffered JSON parsing** — was blank. Goal added, ADR-0007 referenced.
9. **Add structured output validation with Pydantic + retry/repair** — was blank; highest-priority fix, since the original implementation had a real documented defect. Goal + ADR-0005 + **Correction**: validation was shape-only (F-01) — a reply could validate while disagreeing with `check_eligibility`, or without it being called at all. Fixed by `verify_decision()` and reworking `log_claim` to take flight facts instead of a model-authored judgment; prompt bumped to v4.
10. **Add retries/backoff, timeouts, fallback model, idempotency** — was blank, and the title itself now overstates what shipped: the idempotency mechanism it named was implemented then removed. Goal deliberately drops the idempotency claim; **Correction** notes the `idempotency-key` header was confirmed unsupported by Anthropic's Messages API and removed (F-04) — idempotency belongs at `log_claim`/`issue_payment` in W2, keyed by `claim_id`, not at the LLM-call layer. Title left as-is; flagged for a human decision rather than renamed unilaterally.
11. **W1 Review/Refactoring** — was blank, despite being the correction pass itself. Goal: audit W1 against its own documented claims before the W2 LangGraph rebuild, and fix what the audit found. Bullets note 14 findings, 6 fixed via T-1…T-6; PR #13, ADR-0003 and ADR-0006 referenced.

## Cross-cutting findings

- 7 of 11 pages were blank despite "Done" status.
- No page had a Correction field before this pass — the two tasks with a documented post-hoc defect showed no trace of it in Notion.
- Task 10's title is stale relative to current code; left for a human rename decision.
