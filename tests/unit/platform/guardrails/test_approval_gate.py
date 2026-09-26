"""Pins the deny-all stub: every guarded action must be denied, unconditionally."""

import pytest

from ombuds.platform.guardrails.approval_gate import GuardedAction, check_approval


@pytest.mark.parametrize("action", list(GuardedAction))
def test_every_guarded_action_is_denied(action: GuardedAction) -> None:
    decision = check_approval(action)

    assert decision.approved is False
    assert decision.reason
