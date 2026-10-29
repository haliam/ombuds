# `py-review` Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `py-review` Claude Code skill in the ombuds repo: a PR-oriented Python review with separate rubric files, a fixed report, and a severity-first output.

**Architecture:** A short `SKILL.md` holds only the workflow. Rules live in rubric files (`core`, `solid`, `fastapi`, `agentic`, `testing`) loaded per lens. A `report-template.md` fixes the output. Everything is Markdown, so "tests" are a small format-check script plus three dry runs on real branches (spec section 10).

**Tech Stack:** Markdown skill files, Python 3 for the throwaway checker, git. No new dependencies.

**Spec:** `docs/proposals/py-review-skill-design.md`

## Global Constraints

- Skill path: `.claude/skills/py-review/`; files exactly as in spec section 3: `SKILL.md`, `report-template.md`, `rubric/{core,solid,fastapi,agentic,testing}.md`.
- Frontmatter: `name: py-review`, `disable-model-invocation: true`, `argument-hint: "[paths...] [--base <branch>] [--lens <names>] [--min-severity <level>]"`, plus a one-sentence `description`.
- `SKILL.md` ≤ 4096 bytes. Rubric files contain no ombuds-specific content.
- Rule line format (one per rule): `- **ID** · Severity · check — why`, optionally `Severity (note)`. Severities: Blocker, Major, Minor. IDs are stable once written.
- Thresholds: cognitive complexity ≤ 15 (Minor above, Major above 25); function length ≤ 30 lines; >4 parameters; nesting >3; duplication ≥ 3 near-identical blocks of ≥ 6 lines. The repo's own limits win if set.
- Metrics table is labelled "estimated by Claude, not SonarQube".
- Defaults: base branch `--base`, else `origin/main`, else `main`; sequential up to 10 changed `.py` files, above that one subagent per package directory; `review.md` at repo root; Minor findings capped at 15 in `review.md`.
- The executor has no shell on the owner's machine. Files are written in the workspace and delivered with `device_commit_files`; git commands are run by the owner. One commit for the whole skill, not pushed.
- Access granted so far covers `.claude/skills` and `docs`. Task 5 needs the repo root for `.gitignore`.

## Review Focus

1. Empty diff, or a diff with no `.py` files: say there is nothing to review and ask; write no `review.md`.
2. Repo without `AGENTS.md`, `docs/code-style.md` or a `make lint` target (another repo): skip Step 0 items with a note in the header, no failure.
3. Missing `origin/main` or detached HEAD: fall back to `main`, then ask for `--base`.
4. Deleted or renamed files and generated code: deleted files skipped, renames reviewed once, all listed under "Not reviewed".
5. Clean diff, or unknown `--lens` name: a clean diff gives a short "looks good" report with zero findings and no invented tasks; an unknown lens stops with the valid names listed.

---

### Task 1: Format checker and the `core` + `solid` rubrics

**Files:**
- Create (scratchpad, not committed): `/tmp/claude-0/-home-claude/434dbb03-c86b-5ad3-aa0b-5436bf87d708/scratchpad/check_skill.py`
- Create: `.claude/skills/py-review/rubric/core.md`, `.claude/skills/py-review/rubric/solid.md`

**Interfaces:**
- Produces: `check_skill.py <skill_dir>` exits 0 or prints one line per failure and exits 1. Checks: (a) every rule line matches `^- \*\*([A-Z]+-\d{2})\*\* · (Blocker|Major|Minor)( \(.+\))? · .+ — .+$` in `rubric/*.md`, and IDs are unique across files; (b) `SKILL.md` is ≤ 4096 bytes and its frontmatter has the four keys from Global Constraints; (c) `report-template.md` has the eight headings from Task 3 in order; (d) all seven files exist. Later tasks only run it.
- Produces: rule IDs the report cites. `core.md`: `PY-01` mutable default argument; `PY-02` bare or overbroad `except`; `PY-03` resource without context manager; `PY-04` wildcard import; `PY-05` public API without docstring; `CC-01` function >30 lines; `CC-02` >4 parameters; `CC-03` nesting >3; `CC-04` magic number; `CC-05` boolean flag argument; `CC-06` dead or commented-out code; `CC-07` misleading name; `CC-08` duplicated block; `CC-09` cognitive complexity (Minor >15, Major >25); `PAT-01` a pattern would remove a visible problem; `PAT-02` over-engineering; `SEC-01` hardcoded secret (Blocker); `SEC-02` `eval`/`exec`; `SEC-03` `shell=True`; `SEC-04` SQL by string concatenation; `SEC-05` weak hashing. `solid.md`: `SRP-01`, `OCP-01`, `LSP-01`, `ISP-01`, `DIP-01` (default Major).

- [x] **Step 1: Write `check_skill.py`** with the four checks above.
- [x] **Step 2: Run it against the not-yet-existing skill dir.** Run: `python3 check_skill.py <repo>/.claude/skills/py-review`. Expected: FAIL, "missing file" lines for all seven files.
- [x] **Step 3: Write `core.md` and `solid.md`.** One rule line per ID above, each with severity, a one-line check and a one-line why. Open `core.md` with two sentences: the lens always applies, and tool-enforced style (formatting, naming, imports, types) is out of scope when the repo says so. Add the metrics table from spec section 6 at the end of `core.md`.
- [x] **Step 4: Run the checker.** Expected: rule-format and uniqueness checks pass; remaining failures are only the not-yet-written files.

### Task 2: Stack lens rubrics

**Files:**
- Create: `.claude/skills/py-review/rubric/fastapi.md`, `agentic.md`, `testing.md`

**Interfaces:**
- Consumes: the rule line format and checker from Task 1.
- Produces: `FA-01` to `FA-06` (thin routers; `Depends` not globals; Pydantic at boundaries with `response_model`; no blocking I/O in `async def`; errors via `HTTPException`/handlers; one config object), `AG-01` to `AG-06` (prompts and tool schemas apart from logic; typed validated tool I/O; timeouts, retries and a loop cap; no secrets or full prompts in logs; LLM client behind an interface; model output never executed or interpolated unvalidated; `AG-06` is Blocker), `TS-01` to `TS-04` (new behaviour has a test; deterministic with LLM/network mocked; no inter-test dependency; testable design). Each file opens with its detection trigger from spec section 4 Step 3, and a line that repo rules for the same area take precedence.

- [x] **Step 1: Run the checker.** Expected: unchanged failures (three files missing).
- [x] **Step 2: Write the three files** with one rule line per ID above and the trigger sentence on top.
- [x] **Step 3: Run the checker.** Expected: only `SKILL.md` and `report-template.md` missing; no format or duplicate-ID failures.

### Task 3: Report template

**Files:**
- Create: `.claude/skills/py-review/report-template.md`

**Interfaces:**
- Produces: eight `##` headings in this order: `1. Header`, `2. Verdict`, `3. Severity overview`, `4. Findings`, `5. Fix order`, `6. Rule conflicts`, `7. Estimated metrics`, `8. Not reviewed / considered and left alone`.

- [x] **Step 1: Run the checker.** Expected: FAIL on missing `report-template.md`.
- [x] **Step 2: Write the template** in the style of `codebase-review/report-template.md`: placeholders in angle brackets, one-line instruction per section. Header carries scope, base, lenses, `make lint` result, date, branch, short SHA. Verdict is one of Approve / Approve with comments / Changes requested plus 2 to 3 lines. Overview is the lens × severity table with totals (counts include findings hidden by `--min-severity`). Findings has three subsections Blocker, Major, Minor; each finding has fixed fields `[ID] file:line`, lens, problem, why it matters, fix snippet; Minor capped at 15 with a per-rule count for the rest. Rule conflicts has the five fields from spec section 5.3 and is omitted if empty. Metrics carries the "estimated by Claude, not SonarQube" label.
- [x] **Step 3: Run the checker.** Expected: heading-order check passes; only `SKILL.md` missing.

### Task 4: `SKILL.md` workflow

**Files:**
- Create: `.claude/skills/py-review/SKILL.md`

**Interfaces:**
- Consumes: rubric file names (Tasks 1 and 2) and `report-template.md` (Task 3).
- Produces: the invocable skill `/py-review`.

- [x] **Step 1: Run the checker.** Expected: FAIL, `SKILL.md` missing.
- [x] **Step 2: Write `SKILL.md`** in `codebase-review`'s style: frontmatter from Global Constraints, a "read-only except `review.md`" opening, then Inputs (`$ARGUMENTS`: paths, `--base`, `--lens` with valid names `core,solid,fastapi,agentic,testing`, `--min-severity`), then Steps 0 to 5 from spec section 4, then rule precedence (spec section 5, all four points), then the constraints from spec section 9. It must state the handling for each Review Focus item: empty diff or no `.py` files, missing repo docs or `make lint`, missing base branch, deleted/renamed/generated files, clean diff, unknown lens name.
- [x] **Step 3: Run the checker.** Expected: PASS, exit 0 (size ≤ 4096 bytes, frontmatter keys present, all files exist).
- [x] **Step 4: Spot-check handling lines.** Run: `grep -ciE "nothing to review|unknown lens|looks good|origin/main|Not reviewed" SKILL.md`. Expected: at least 5. Result: 4 (the matched phrases share lines); all six handlings are present.

### Task 5: Wire-in and dry runs

**Files:**
- Modify: `.gitignore` at the repo root (add `review.md`); needs folder access to the repo root.
- Deliver the skill folder to the owner's repo with `device_commit_files`.

**Interfaces:**
- Consumes: the complete skill from Tasks 1 to 4.

- [x] **Step 1: Request access to the repo root** and add `review.md` to `.gitignore` (skip if already present).
- [x] **Step 2: Deliver the files** to `/home/haliam/Repos/ombuds/.claude/skills/py-review/` and run the checker on that path. Expected: PASS.
- [ ] **Step 3: Dry runs (owner, in Claude Code in the repo).** Run `/py-review` on: a small diff; a diff touching FastAPI routes; a diff touching agent or tool code. Expected for each: findings carry `file:line` and a rule ID; no formatting, naming or type findings that `make lint` owns; lens list in the header matches the files; severity overview totals equal the number of findings; `review.md` exists at the repo root.
- [ ] **Step 4: Edge runs.** `/py-review --lens nonsense` stops listing the valid names; `/py-review` on a branch with no changes asks instead of writing `review.md`; a second run on the same diff gives the same finding IDs.
- [x] **Step 5: Commit (owner).** `git add .claude/skills/py-review .gitignore docs/proposals/py-review-skill-design.md docs/proposals/py-review-skill-plan.md` then one commit `feat: add py-review skill`. Do not push.
