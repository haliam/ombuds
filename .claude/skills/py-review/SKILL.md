---
name: py-review
description: PR-oriented review of changed Python code against best practice, SOLID, clean code and Sonar-style metrics. Use before opening a PR. Read-only except review.md.
disable-model-invocation: true
argument-hint: "[paths...] [--base <branch>] [--lens <names>] [--min-severity <level>]"
---

# Python PR review (report only)

Review changed Python code and write one report. **Do not modify code.** `review.md` at the repo root is the only file you create.

## Inputs (`$ARGUMENTS`)
- paths — files to review. Without them, review the PR diff.
- `--base <branch>` — diff base. Default `origin/main`, else `main`; if neither exists (or HEAD is detached with no base), ask for `--base`.
- `--lens <names>` — comma-separated from `core,solid,fastapi,agentic,testing`. Exactly those are loaded. An unknown name stops the run and lists the valid names.
- `--min-severity <blocker|major|minor>` — hide findings below it; counts still include them. Default `minor`.

## Steps
0. **Ground.** Read `AGENTS.md`, `docs/code-style.md`, `docs/decisions/` titles, and `[tool.ruff.lint]` / `[tool.mypy]` in `pyproject.toml`; list rubric rules whose `[ruff: codes]` tag is enabled for the file (see precedence). Run `make lint` and record the result. Anything missing (docs, config, a `make lint` target) is skipped with a note in the header, not a failure.
1. **Scope.** Paths, else `git diff <base>...HEAD`. Keep `.py` only. Skip deleted, generated, migration and vendored files; review a rename once; list all under "Not reviewed". If the diff is empty or has no `.py` files: say there is nothing to review, ask what to review, and write no `review.md`.
2. **Context.** Read changed lines first, then only callers, base classes and the matching test needed to judge them. Do not review untouched code.
3. **Lenses.** `core` and `solid` always; `fastapi` if files import `fastapi`/`pydantic` or sit under `api/`; `agentic` if they call an LLM client, define tools or hold an agent loop/graph node; `testing` if logic or `tests/` changed. State them in the header.
4. **Review.** Read each loaded `rubric/<lens>.md`. Tie every finding to a changed line (or code a change directly affects) and cite its rule ID.
5. **Report.** Follow `report-template.md` exactly, write `review.md`, then print in chat: verdict, severity overview, Blockers and Majors, and the path. Same diff, same findings and IDs.
   Clean diff: a short "looks good" report, zero findings.

Large diffs: sequential up to 10 changed `.py` files; above that, one subagent per package directory, then merge and de-duplicate.

## Precedence
1. Tool-enforced concerns (formatting, import order, naming, types) are not re-reviewed. `make lint` passing is a fact; failures on changed files are Major.
2. A rule with `[ruff: codes]` is skipped for a file when any code is enabled (via `select`/`extend-select`, prefix or `ALL`; not in `ignore` or a matching `per-file-ignores`; default `E4,E7,E9,F` if no `select`). List skipped IDs in the header. If the code exists but is off, keep the rule and add "ruff <code> could enforce this". Untagged rules always stay.
3. Repo rules (`AGENTS.md`, `docs/code-style.md`, ADRs) beat rubric rules; code breaking one is a finding citing the repo rule. Real conflicts go in "Rule conflicts": repo rule and source, rubric ID, applied (repo), and Sound / Questionable / Outdated / Unverified with a one-line reason. The assessment never changes severity or verdict.
4. The repo's own thresholds win over the rubric defaults.

## Constraints
Inspect before recommending. An alternative pattern existing is not a reason to change. No over-engineering. No preference-based advice. Preserve behaviour unless clearly wrong. Minor findings: cap 15 in `review.md`, rest as per-rule counts; chat shows Blockers and Majors only. Never invent tasks. Metrics are "estimated by Claude, not SonarQube".
