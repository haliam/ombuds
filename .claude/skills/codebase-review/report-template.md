# <Done> Review & Pre-<Next> Plan

_Reviewed <date> on branch `<branch>` (`main` @ `<sha>`). `make lint`: <result>. `tests/unit`: <n passed>. Integration/e2e: <run or read only>._

---

## 1. Current Project State
Architecture, structure, technologies, what runs today, what is still scaffold, overall state — from the actual code.

## 2. <Done> Assessment
A table: stage task | implemented in | verdict (consistent with architecture and standards? gaps?). Include carry-over from the previous review and any drift between docs and code.

## 3. Findings
One block per finding:

### F-NN — <title>
- **Area:**
- **Current situation:**
- **Problem / risk:**
- **Recommended change:**
- **Reason:**
- **Priority:** Critical / High / Medium / Low
- **Estimated complexity:** Small / Medium / Large
- **Must fix before <Next>:** Yes / No

## 4. Required Refactoring Before <Next>
Only changes that genuinely must land first, in implementation order. Per task:
### P-N — <title>
- **Description:**
- **Files/modules likely affected:**
- **Reason:**
- **Acceptance criteria:**
- **Dependencies:**

## 5. Optional Improvements
Meaningful only; do not inflate. Table: ID | improvement | when.

## 6. Proposed Pre-<Next> Execution Plan
- [ ] P-1 — …
- [ ] P-2 — …

## 7. Final Recommendation
Exactly one of: **Ready for <Next>** / **Ready for <Next> after the required refactoring** / **Not ready for <Next>** — then the reasoning from the findings, plus "Considered and left alone".
