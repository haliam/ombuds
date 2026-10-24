"""Agent eval: run the real triage agent over the labelled claims and report where it diverges from the gold.

Needs ANTHROPIC_API_KEY and, because the agent may call `search_kb`, an ingested knowledge base and
OPENAI_API_KEY (`make eval-agent` starts the db and ingests first). Approvals go to an in-memory gate, so
nothing is written to Postgres. Each case is a handful of real model turns and the process spend cap
(ADR-0018) applies: a case the cap refuses is reported as an error, not a failure of the agent.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from evals.agent_dataset import AgentCase, Outcome, load_cases
from ombuds import config
from ombuds.features.claims_triage.application.triage_use_case import TriageResult, run_triage
from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.guardrails.approval_gate import ApprovalGate
from ombuds.platform.infrastructure.postgres import create_pool
from ombuds.platform.infrastructure.repositories import PostgresClaimRepository

ERROR = "error"


@dataclass(frozen=True)
class CaseScore:
    """How one run compared with its case. `actual` is `error` when the run raised; the checks are then False."""

    case_id: str
    expected: Outcome
    actual: Outcome | str
    outcome_ok: bool
    verdict_ok: bool | None
    """Decision cases only: eligibility, amount and reasons all match the rules engine on the gold facts."""
    called_eligibility: bool | None
    """Decision cases only: the run called `check_eligibility` (a sanity check: decisions are verified against it)."""
    detail: str = ""


def outcome_of(result: TriageResult) -> Outcome:
    """How a run ended: escalated, a verified decision, or (neither) a clarifying question."""
    if result.escalated:
        return "escalate"
    return "decision" if result.decision is not None else "clarify"


def score_case(case: AgentCase, result: TriageResult) -> CaseScore:
    """Compare one run with its case: did it end the right way and, for decisions, reach the right verdict."""
    actual = outcome_of(result)
    expected = case.expected()
    verdict_ok: bool | None = None
    called: bool | None = None
    detail = ""
    if expected is not None:
        called = any(r.name == "check_eligibility" for r in result.tool_results)
        decision = result.decision
        verdict_ok = (
            decision is not None
            and decision.eligible == expected.eligible
            and (decision.compensation_amount_eur or 0) == expected.compensation_eur
            and tuple(decision.reason_codes) == tuple(expected.reasons)
        )
        if not verdict_ok:
            got = "no decision"
            if decision is not None:
                got = f"{decision.eligible}/{decision.compensation_amount_eur}/{decision.reason_codes}"
            detail = f"expected {expected.eligible}/{expected.compensation_eur}/{expected.reasons}, got {got}"
    elif actual == "escalate" and result.escalation_reason:
        detail = result.escalation_reason
    return CaseScore(case.id, case.outcome, actual, actual == case.outcome, verdict_ok, called, detail)


def run_case(case: AgentCase, run: Callable[[str], TriageResult]) -> CaseScore:
    """Run and score one case; a raised exception becomes an `error` score so one bad run cannot end the eval."""
    try:
        return score_case(case, run(case.claim))
    except Exception as exc:  # report-only eval: record and move on
        return CaseScore(case.id, case.outcome, ERROR, False, None, None, f"{type(exc).__name__}: {exc}")


def report(scores: list[CaseScore]) -> str:
    """Format outcome accuracy overall and per expected outcome, the verdict rate for decisions, and every miss."""
    lines = [f"{len(scores)} cases", ""]
    by_outcome = Counter(s.expected for s in scores)
    ok_by_outcome = Counter(s.expected for s in scores if s.outcome_ok)
    lines.append(f"outcome correct:   {sum(s.outcome_ok for s in scores)}/{len(scores)}")
    for outcome in ("decision", "clarify", "escalate"):
        if by_outcome[outcome]:
            lines.append(f"  {outcome:<9} {ok_by_outcome[outcome]}/{by_outcome[outcome]}")
    decisions = [s for s in scores if s.verdict_ok is not None]
    lines.append(f"verdict correct:   {sum(bool(s.verdict_ok) for s in decisions)}/{len(decisions)} decision cases")
    lines.append(f"errors:            {sum(s.actual == ERROR for s in scores)}")

    misses = [s for s in scores if not s.outcome_ok or s.verdict_ok is False or s.called_eligibility is False]
    lines += ["", "misses:"]
    if not misses:
        lines.append("  none")
    for s in misses:
        lines.append(f"  {s.case_id}: expected {s.expected}, got {s.actual}" + (f" — {s.detail}" if s.detail else ""))
    return "\n".join(lines)


def main() -> None:
    """Run the agent over every case against the configured Postgres and models and print the report."""
    pool = create_pool(config.database_url(), config.DATABASE_POOL_MAX_SIZE)
    try:
        registry = build_tool_registry(ApprovalGate(), PostgresClaimRepository(pool))

        def run(claim: str) -> TriageResult:
            return run_triage(claim, registry=registry)

        print(report([run_case(case, run) for case in load_cases()]))
    finally:
        pool.close()


if __name__ == "__main__":
    main()
