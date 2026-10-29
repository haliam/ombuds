# `py-review` skill — design

_Status: draft for owner review · 2026-10-28 · supersedes nothing. Throwaway once the skill is implemented and its description in `SKILL.md` is the source of truth._

## 1. Purpose

A repeatable, PR-oriented code review for Python files, run locally by the developer before opening a PR. It checks the changed code against Python best practices, SOLID, clean-code and design-pattern principles, and Sonar-style quality metrics, and it respects the repo's own standards.

**Stated by the owner:** local only (CI is a later, separate skill); invoked in Claude Code; usable on the ombuds FastAPI agentic repo and, later, other repos; reviews named files, otherwise the PR diff, otherwise asks; output is a chat summary plus a saved `review.md`; Sonar metrics are emulated, not measured; stack lenses switch on automatically; when a repo rule overrides a generic rule, the report says which and whether the repo rule is sound.

**Assumptions (correct me):** it reports and suggests, it never edits code; manual invocation only, like `codebase-review`; `review.md` is a throwaway for the PR description, kept out of git.

**Success looks like:** two runs on the same diff give the same findings in the same format; every finding is anchored to a changed line and cites a rule; no style noise that `ruff`/`mypy` already own; a clean diff gets a short "looks good" report, not invented tasks.

## 2. Non-goals

- No CI integration, no JSON output, no PR comment posting (the rubric files are kept separate so a CI skill can reuse them later).
- No real SonarQube/ruff/radon metrics; the metrics table is labelled "estimated by Claude, not SonarQube".
- No whole-repo audit (that is `codebase-review`) and no code changes.

## 3. Files and invocation

```
.claude/skills/py-review/
├── SKILL.md            # workflow only (~3 KB, same frontmatter style as codebase-review)
├── report-template.md  # fixed report format
└── rubric/
    ├── core.md         # best practices, clean code, patterns, Sonar-style thresholds
    ├── solid.md        # SRP, OCP, LSP, ISP, DIP
    ├── fastapi.md      # loaded when detected
    ├── agentic.md      # loaded when detected
    └── testing.md      # loaded when detected
```

Frontmatter: `name: py-review`, `disable-model-invocation: true`, `argument-hint: "[paths...] [--base <branch>] [--lens <names>] [--min-severity <level>]"`. Invoked as `/py-review`, `/py-review src/ombuds/api/routes.py`, `/py-review --base develop`, `/py-review --lens solid,fastapi`, `/py-review --min-severity major`.

- `--lens <names>`: comma-separated subset of `core`, `solid`, `fastapi`, `agentic`, `testing`. Default: every lens that applies (Step 3). A named lens is loaded even if detection would not select it.
- `--min-severity <blocker|major|minor>`: hide findings below that level from the report. Default `minor` (everything). Counts of hidden findings are still shown.

Portability: only Step 0 below mentions repo documents, and it skips whatever does not exist. Rubric files contain no ombuds-specific content.

## 4. Workflow

**Step 0 — ground in the repo.** Read `AGENTS.md`, `docs/code-style.md` and the ADR titles in `docs/decisions/` if present. Read `[tool.ruff.lint]` (`select`, `extend-select`, `ignore`, `per-file-ignores`) and `[tool.mypy]` in `pyproject.toml` to learn what tools already enforce, including any complexity limit; build the list of rubric rules that ruff already covers (section 5.1). Run `make lint` and record the result in the report header. If a document or target is missing, skip it and say so.

**Step 1 — scope.** In order: (1) paths from the arguments; (2) the diff `git diff <base>...HEAD`, with `<base>` from `--base`, else `origin/main`, else `main`; (3) if both are empty, ask. Keep `.py` files only; skip generated files, migrations and vendored code, and list them under "Not reviewed".

**Step 2 — context.** Read the changed lines first, then only what is needed to judge them: callers, base classes, the matching test module. Do not review untouched code, except where a change makes it wrong.

**Step 3 — lens selection.** If `--lens` is given, use exactly those. Otherwise `core` always (best practice, clean code, patterns and the Sonar-style metrics); `solid` always; `fastapi` if the files import `fastapi`/`pydantic` or sit under an `api/` package; `agentic` if they call an LLM client, define tools, or contain an agent loop/graph node; `testing` if the diff adds or changes logic or touches `tests/`. State the lenses applied in the header.

**Step 4 — review.** Apply the loaded rubric files. Precedence is in section 5. Each finding is tied to a changed line (or code a change directly affects).

**Step 5 — report.** Fill `report-template.md`, write `review.md` at the repo root, then print the verdict, the blockers/majors and the path in chat.

**Parallelism.** One sequential pass up to 10 changed `.py` files. Above that, split by package directory and use one subagent per group, then merge and de-duplicate findings. These are defaults and can be changed in `SKILL.md`.

## 5. Rule precedence and rule conflicts

1. **Tool-enforced concerns are out.** If the repo states that formatting, import order, naming or types are enforced by tools (as `docs/code-style.md` does), the skill does not re-review them. Passing `make lint` is reported as a fact; failures on changed files are listed as Major.
   - **Rubric rules that ruff already covers are skipped.** A rule carries a `[ruff: <codes>]` tag when ruff has an exact equivalent (section 6). The rule is skipped for a file when any listed code is enabled for it: covered by `select`/`extend-select` (a code, its prefix, or `ALL`), not in `ignore`, and not in a `per-file-ignores` entry matching the file. If `select` is absent, ruff's defaults apply (`E4`, `E7`, `E9`, `F`). The report header lists the skipped rule IDs.
   - If the equivalent exists but is not enabled, the rule stays on and the finding adds "ruff `<code>` could enforce this".
   - Rules without a tag (approximate matches such as cognitive complexity against `C901`) always stay on.
2. **Repo rules win.** `AGENTS.md`, `docs/code-style.md` and ADRs override any rubric rule that disagrees. Code that breaks a repo rule is a finding that cites the repo rule, not the rubric.
3. **Conflicts are surfaced, not hidden.** When a repo rule overrides a rubric rule, the report's "Rule conflicts" section gives one entry:
   - the repo rule and its source (`file`, section);
   - the rubric rule it overrides (ID);
   - which was applied (always the repo rule);
   - an assessment of the repo rule with one verdict and a one-line reason: **Sound** (justified by an ADR or a documented constraint), **Questionable** (contradicts accepted practice and nothing in the repo explains why), **Outdated** (code, ADRs or tooling moved on), or **Unverified** (cannot be judged from the repo; say what to check).
4. The assessment is advice for the owner. It never changes a finding's severity or the verdict. Only real conflicts are listed; a repo rule that is merely stricter or looser is not one.

_Candidates already visible in `docs/code-style.md`:_ "functions by default, a class when there is state" against the OCP/DIP rubric rules that favour polymorphism and injected abstractions; "models are frozen by default"; "docstrings on every public function" against the minimal-docs stance of some clean-code guidance. The first run will confirm which are real conflicts.

## 6. Rubric content (`rubric/core.md` and `rubric/solid.md`)

The SOLID rows below live in `solid.md`; the others in `core.md`. Every rule has an ID, a one-line check, a default severity and a short "why", and ends with a `[ruff: <codes>]` tag when ruff has an exact equivalent: `PY-01` B006; `PY-02` E722, BLE001; `PY-03` SIM115; `PY-04` F403; `PY-05` D100–D107; `CC-02` PLR0913; `CC-04` PLR2004; `CC-05` FBT001, FBT002; `CC-06` ERA001; `SEC-01` S105, S106, S107; `SEC-02` S102, S307; `SEC-03` S602, S604; `SEC-04` S608; `SEC-05` S324.

| Area | IDs | Examples |
|---|---|---|
| Python best practice | `PY-` | mutable default args, bare/overbroad `except`, context managers for resources, no wildcard imports, public APIs documented. Style/naming/types rules are skipped when tool-enforced (section 5.1). |
| SOLID | `SRP-`, `OCP-`, `LSP-`, `ISP-`, `DIP-` | class/function with several jobs; long `if/elif` on a type; subclass breaking the base contract; fat protocol; high-level code constructing concrete dependencies |
| Clean code | `CC-` | function >30 lines, >4 parameters, nesting >3, magic numbers, boolean flag arguments, dead or commented-out code, misleading names |
| Patterns | `PAT-` | recommend Strategy/Factory/Adapter/Repository only when it removes a visible problem; flag over-engineering as a finding too |

**Estimated Sonar-style thresholds (emulated; the repo's own limits win if set):**

| Metric | Default |
|---|---|
| Cognitive complexity per function | ≤ 15 (Minor above, Major above 25) |
| Function length | ≤ 30 lines (soft) |
| Duplication | ≥ 3 near-identical blocks of ≥ 6 lines |
| Categories counted | bug, vulnerability, code smell, security hotspot |
| Security checks | hardcoded secrets, `eval`/`exec`, `shell=True`, SQL string concatenation, weak hashing |

**Severity.** Blocker: probable bug, security vulnerability, data-loss risk. Major: clear SOLID violation, complexity >25, new logic without a test, `make lint` failure. Minor: small smells.

## 7. Stack lenses

- **`fastapi.md`** — thin routers, logic in services; dependencies through `Depends`, not globals; Pydantic models at request/response boundaries with `response_model`; no blocking I/O inside `async def`; errors via `HTTPException` or handlers; settings from one config object.
- **`agentic.md`** — prompts and tool schemas separate from business logic; typed, validated tool inputs and outputs; timeouts, retries and a loop-iteration cap on LLM/HTTP calls; no secrets or full prompts/responses in logs; LLM client behind an interface; model output never executed or interpolated into SQL/shell unvalidated.
- **`testing.md`** — new or changed behaviour has a test; tests are deterministic with LLM/network mocked; no inter-test dependencies; code under review is testable (injected dependencies, no hidden state).

Where the repo defines its own rules for these areas (for example business-rule placement and test layout in `docs/code-style.md`), they take precedence per section 5.

## 8. Report (`report-template.md`)

1. **Header** — scope (files, base branch), lenses applied, `make lint` result, rule IDs skipped because ruff enforces them, date, branch and short SHA.
2. **Verdict** — Approve / Approve with comments / Changes requested, plus a 2–3 line summary.
3. **Severity overview** — a table of counts, lens × severity (Blocker / Major / Minor), with totals. It gives the severity range of the whole review at a glance and includes findings hidden by `--min-severity`.
4. **Findings** — one list per severity, in the order Blocker, Major, Minor, merging all lenses. Inside a severity, ordered by file then line. Each finding: `[ID] file:line`, lens tag, problem, why it matters, short fix snippet. Fixed fields so runs are comparable.
5. **Fix order** — a short numbered list: all Blockers, then Majors, then the Minors worth doing in this PR; the rest are left to follow-up.
6. **Rule conflicts** — per section 5.3; omitted if there are none.
7. **Estimated metrics** — complexity of touched functions, duplication, counts by category; labelled "estimated by Claude, not SonarQube".
8. **Not reviewed / considered and left alone** — skipped files, out-of-scope items, and patterns that exist but were left as they are.

**Noise control.** `review.md` lists every Blocker and Major. Minor findings are capped at 15, chosen by impact; the rest are summarised as a count per rule ID. The chat message shows the verdict, the severity overview, and the Blockers and Majors only.

## 9. Constraints (carried over from `codebase-review`)

Inspect before recommending. An alternative pattern existing is not a reason to change. No over-engineering and no abstraction without a concrete benefit. No recommendations from personal preference. Preserve behaviour unless it is clearly wrong. If the code is good, say so and keep the findings short; do not invent tasks.

## 10. Verification before first use

Run the skill on three real branches: a small diff, a diff touching FastAPI routes, and a diff touching agent/tool code. Check that findings are line-anchored and cite rules, that nothing `ruff`/`mypy` owns is re-reported, that lens selection matches the files, that a repeat run on the same diff gives the same findings, and that any real conflicts appear in "Rule conflicts".

## 11. Implementation notes

- Add `review.md` to `.gitignore`.
- Skill files are committed in one commit; not pushed.
- **One skill, not several (decided).** Responsibilities are separated by rubric file and `--lens`, not by skill. Revisit and split by lens if, after three real runs, reports are noisy, or `SKILL.md` grows past about 4 KB. A split only copies the workflow, since the rubric files are already separate.
- Rubric wording follows the writing-skills guidance: rules short, one check per line, IDs stable.
