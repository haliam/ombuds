---
name: docs-cleanup
description: Audit the ombuds docs and write a plan of what to keep, update, trim, merge or delete (outdated, duplicated or history-only files). Read-only except for the plan file. Use when asked to simplify, clean up, prune or audit the documentation.
argument-hint: "[folder or scope, default: all docs]"
---

# Audit the docs and propose a cleanup

Goal: keep the knowledge a new reader or an interviewer needs, and remove what is outdated, duplicated or only history. **Edit nothing except the plan file** `docs/proposals/docs-cleanup-plan.md`. The plan is a throwaway: it is deleted when its cleanup is done.

Scope: `docs/` (all subfolders), `README.md`, `AGENTS.md`, `CLAUDE.md`, `.claude/skills/*.md`. If an argument names a folder, audit only that. Out of scope: source code, ADR content (only flag a wrong Status line), `kb_seed/*.md` (product data).

## Repo facts to respect
- `docs/decisions/` ADRs are the decision record: KEEP. A superseded ADR stays, with its Status line.
- `docs/reports/` holds one-off run reports (history by design): keep unless a report is fully absorbed elsewhere.
- `docs/proposals/` holds plans. A plan marked done is HISTORY.
- `docs/progress/` holds `tasks.md` (board), `task_summaries.md` (short recaps) and `glossary.md`; summaries keep their headings because the glossary and `tasks.md` link to the anchors.
- `docs/diagrams/<slug>/` keeps `README.md`, plus `.json` and `.png` for archify diagrams. The `.html` is a build output and is not committed. Every diagram needs a row in `docs/diagrams/README.md`.
- Review files (`w*_review_*.md`) are deleted once their tasks are done; git history keeps them.

## Method
1. **Inventory.** For each doc: lines and size, last commit date (`git log -1`), and who links to it (grep the repo for the file name). Include non-markdown files in `docs/` and their total weight (`du`).
2. **Classify.** LIVING (describes the system or a rule as it is today), HISTORY (a plan, review or report for finished work), or SNAPSHOT (a board or log that goes stale).
3. **Verify before judging.** Every "stale" claim cites evidence: a status line that says done, a task ticked in `tasks.md`, a Makefile target that no longer exists, a "Planned" section whose work shipped. Never judge from a title alone. Mark anything not checked as **unverified**.
4. **Find overlap.** Two docs answering the same question: name the source of truth.
5. **Check links.** Every delete or merge lists the inbound links to fix.

## One action per doc
KEEP · UPDATE (quote the stale passage) · TRIM (name the section to cut) · MERGE INTO `<file>` (then delete) · DELETE (say what holds the information now; git keeps the file) · ASK (the owner's call, or you cannot tell).

## Output: `docs/proposals/docs-cleanup-plan.md`
- Status line and a summary: counts per action and the size saved.
- One table per folder: file, class, action, evidence, inbound links to fix.
- Proposed commits: small and ordered, one per task, each with its verification (grep for dead links, `make lint`).
- Open questions for the owner.

Be specific and short. Recommend, do not survey. Never delete or edit anything yourself: the owner approves the plan first, then the commits run in a separate chat, one per task (AGENTS.md).
