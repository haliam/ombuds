import pytest

import ombuds.features.claims_triage.tools.issue_payment as issue_payment_module
from ombuds.domain.errors import ToolExecutionError
from ombuds.features.claims_triage.tools.issue_payment import ISSUE_PAYMENT_TOOL, IssuePaymentArgs, issue_payment
from ombuds.platform.guardrails.approval_gate import ApprovalDecision


def _args(**overrides) -> IssuePaymentArgs:
    fields = dict(claim_id="claim-1", amount_eur=250)
    return IssuePaymentArgs(**(fields | overrides))


def test_issue_payment_is_denied_by_the_approval_gate_stub() -> None:
    result = issue_payment(_args())

    assert result.issued is False
    assert "approval_gate stub" in result.reason


def test_issue_payment_raises_tool_execution_error_once_approved(monkeypatch) -> None:
    """Disbursement isn't implemented yet — an approved decision must raise ToolExecutionError, not
    crash the triage turn with NotImplementedError (see ToolRegistry.dispatch)."""
    monkeypatch.setattr(
        issue_payment_module, "check_approval", lambda action: ApprovalDecision(approved=True, reason="approved")
    )

    with pytest.raises(ToolExecutionError, match="not implemented"):
        issue_payment(_args())


def test_issue_payment_args_requires_nonempty_claim_id() -> None:
    with pytest.raises(ValueError):
        IssuePaymentArgs(claim_id="", amount_eur=250)


def test_issue_payment_args_requires_positive_amount() -> None:
    with pytest.raises(ValueError):
        IssuePaymentArgs(claim_id="claim-1", amount_eur=0)


def test_tool_definition_args_model_is_issue_payment_args() -> None:
    assert ISSUE_PAYMENT_TOOL.args_model is IssuePaymentArgs
