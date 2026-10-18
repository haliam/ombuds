---
name: codebase-review
description: Pre-stage technical audit of the ombuds codebase. Use when asked to review the codebase, audit the project before the next week/stage, or produce a "review & pre-<next> plan". Read-only; writes one Markdown report.
disable-model-invocation: true
argument-hint: "[stage-just-finished] [next-stage] [--scope <path>]"
---

# Codebase review (audit and planning only)

Perform a senior Python/AI engineer review of the project as it exists now, and write one report. **Do not modify code.** The report is the only file you create.

## Inputs (`$ARGUMENTS`)
- `<done> <next>` — e.g. `W4 W5`: the stage just finished and the one about to start. If missing, infer from `docs/progress/tasks.md` (last fully checked week and the next), and say what you inferred.
- `--scope <path>` — optional: audit only that area (e.g. `src/ombuds/platform/guardrails`). Without it, review the whole project.
- Output: `docs/progress/<done>_review_pre_<next>_plan.md` (lowercase stage names, matching earlier reviews there). With `--scope`: `docs/progress/review_<scope-slug>.md`.

## Step 0 — ground yourself
Read `AGENTS.md`, `docs/code-style.md`, the ADR list in `docs/decisions/`, `docs/progress/tasks.md`, and the most recent review in `docs/progress/`. Check for a `.codegraph/` index and use it before grep if present.

## Step 1 — inspect the actual code before judging
- Run `make lint` and `uv run pytest tests/unit`; record the results in the report header. Do not run integration/e2e unless asked (they need Docker and keys) — read them instead.
- Map the layout, then read the code paths the finished stage touched. Check dependency direction (`features → platform → domain`) with grep.
- **Claims vs code:** for every invariant the README, ADRs or AGENTS.md assert (e.g. "executes exactly once", "fails closed", "never logged"), find the code that enforces it and a test that pins it. An asserted-but-unenforced invariant is a top finding.
- **Carry-over:** list the previous review's open items and state which were done, so nothing is silently dropped or repeated.

## Evaluate against
Python/modern-Python practice, AI/ML project practice, SOLID, clean code, separation of concerns, dependency direction, package structure, typing, error handling, configuration, logging, testing/pytest, testability and DI, duplication, naming, async/sync, API design, data models and validation, security and secrets, maintainability, consistency of existing patterns, documentation only where genuinely necessary.

## Constraints
1. Inspect before recommending. 2. An alternative pattern existing is not a reason to change. 3. No over-engineering; no abstraction without a concrete benefit. 4. No recommendations from personal preference. 5. Prioritise correctness, maintainability, testability, scalability, developer experience. 6. Preserve behaviour unless clearly wrong. 7. Weigh what the next stage will build on. 8. Be critical but pragmatic: if the code is well structured, say so and keep the task list small; do not invent tasks. List what you considered and left alone.

## Report
Follow `report-template.md` in this directory exactly (seven sections, fixed finding fields). Finish with a short chat summary: verdict, the required tasks, and the report path.
