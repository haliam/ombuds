# Prompt: audit `docs/` and propose what to simplify or delete

Reusable. Paste the block below into a fresh chat (or run it again after a few weeks). Output goes to `docs/proposals/docs-cleanup-plan.md`. The prompt is read-only: it edits no doc except the plan.

```text
Audit every documentation file in this repo and propose what to keep, merge, trim or delete.
Goal: keep the knowledge a new reader or an interviewer needs, and remove what is outdated,
duplicated, or only history. Do not change any doc other than the plan file.

Scope: docs/ (all subfolders), README.md, AGENTS.md, CLAUDE.md, .claude/skills/*.md.
Not in scope: source code, ADR content (ADRs are the decision record; only flag a wrong
Status line), kb_seed/*.md (product data, not docs).

Method
1. Inventory: list every doc with line count and size, last commit date (git log -1) and
   who links to it (grep for the file name across the repo). Include non-markdown
   artifacts in docs/ (html, png, json, py) and their total weight.
2. Classify each doc as one of:
   - LIVING: describes the system or a rule as it is today (architecture, code-style,
     developer guide, ADRs, diagram pages, AGENTS.md).
   - HISTORY: a plan, review or report for work that is already done.
   - SNAPSHOT: a status board or log that goes stale (task list, backlog, summaries).
3. Verify before you judge. For every claim that a doc is stale, cite the evidence:
   a status line that says "done", a task ticked in docs/progress/tasks.md, a command that
   no longer exists in the Makefile, a "Planned" section whose work has shipped. Do not
   call something stale from its title alone.
4. Find overlap: two docs that answer the same question (for example a review and its
   second pass, or three diagrams of the same flow). Say which one is the source of truth.
5. Check links: if a delete or merge breaks inbound links, list each one to fix.

Decide one action per doc
- KEEP: living, accurate, not duplicated.
- UPDATE: living but with a wrong or stale passage (quote the passage).
- TRIM: keep, but cut a named section (for example "original plan follows for reference").
- MERGE INTO <file>: content worth keeping is small; move it, then delete.
- DELETE: history fully absorbed elsewhere. Say what holds the information now, and that
  git history keeps the file.
- ASK: you cannot tell, or it is the owner's call (interview material, personal workflow).

Output: write docs/proposals/docs-cleanup-plan.md with
- Summary: counts per action and the size saved.
- A table per folder: file, class, action, evidence, inbound links to fix.
- Proposed commits: small, ordered, one commit per task, each with its verification
  (grep for dead links, make lint).
- Open questions for the owner.
Rules: be specific and short; recommend, do not survey; mark anything you did not verify
as unverified; never delete or edit anything yourself.
```

## How to run it
1. New chat on a fresh branch from `main`.
2. Paste the block. Read the plan, answer its open questions.
3. Execute the commits in a separate chat, one per task (AGENTS.md rule).
