# py-review — <scope>

## 1. Header
Scope (files reviewed, base branch), lenses applied, `make lint` result (or "skipped: no target"), rule IDs skipped because ruff enforces them, date, branch, short SHA.

_Reviewed <date> on `<branch>` @ `<sha>` against `<base>`. Lenses: <list>. `make lint`: <result>. Skipped (ruff): <IDs>._

## 2. Verdict
One of **Approve** / **Approve with comments** / **Changes requested**, then 2 to 3 lines of summary. A clean diff gets "looks good" and zero findings.

## 3. Severity overview
Table of lens × severity with totals. Counts include findings hidden by `--min-severity`.

| Lens | Blocker | Major | Minor | Total |
|---|---|---|---|---|
| <lens> | <n> | <n> | <n> | <n> |
| **Total** | <n> | <n> | <n> | <n> |

## 4. Findings
Three subsections in this order: Blocker, Major, Minor. Inside one, order by file then line. Minor is capped at 15 by impact; summarise the rest as a count per rule ID. One block per finding:

### <Severity>
- **[<ID>] <file>:<line>**
  - **Lens:** <lens>
  - **Problem:** <what is wrong in this line>
  - **Why it matters:** <consequence>
  - **Fix:** <short snippet or one-line instruction>

## 5. Fix order
Numbered: all Blockers, then Majors, then the Minors worth doing in this PR. The rest are follow-up.

1. <ID> <file>:<line> — <action>

## 6. Rule conflicts
Omit this section if there are none. One entry per real conflict:
- **Repo rule:** <rule> (<file>, <section>)
- **Overrides:** <rubric ID>
- **Applied:** the repo rule
- **Assessment:** Sound / Questionable / Outdated / Unverified — <one-line reason>

## 7. Estimated metrics
_Estimated by Claude, not SonarQube._ Cognitive complexity of touched functions, duplication, counts by category (bug, vulnerability, code smell, security hotspot).

| Function | Cognitive complexity | Lines |
|---|---|---|
| <name> | <n> | <n> |

## 8. Not reviewed / considered and left alone
Skipped files (generated, migrations, vendored, deleted), renames reviewed once, out-of-scope items, and patterns that exist but were left as they are.
