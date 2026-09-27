import pytest

from ombuds.domain.errors import ToolExecutionError
from ombuds.domain.models.claim import EligibilityResult
from ombuds.features.claims_triage.tools import log_claim as log_claim_module
from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL, LogClaimArgs, log_claim
from ombuds.platform.guardrails.approval_gate import ApprovalDecision


def _args() -> LogClaimArgs:
    return LogClaimArgs(
        claim_id="claim-1",
        eligibility=EligibilityResult(eligible=True, compensation_eur=250, reasons=("eligible",)),
    )


def test_log_claim_is_denied_by_the_approval_gate_stub() -> None:
    result = log_claim(_args())

    assert result.logged is False
    assert "approval_gate stub" in result.reason


def test_log_claim_raises_tool_execution_error_once_approved(monkeypatch) -> None:
    """Persistence isn't implemented yet — an approved decision must raise ToolExecutionError, not crash
    the triage turn with NotImplementedError (see ToolRegistry.dispatch)."""
    monkeypatch.setattr(
        log_claim_module, "check_approval", lambda action: ApprovalDecision(approved=True, reason="approved")
    )

    with pytest.raises(ToolExecutionError, match="not implemented"):
        log_claim(_args())


def test_log_claim_args_requires_nonempty_claim_id() -> None:
    with pytest.raises(ValueError):
        LogClaimArgs(claim_id="", eligibility=_args().eligibility)


def test_tool_definition_args_model_is_log_claim_args() -> None:
    assert LOG_CLAIM_TOOL.args_model is LogClaimArgs
