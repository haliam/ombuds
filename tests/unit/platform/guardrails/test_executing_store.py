import pytest
from pydantic import JsonValue

from ombuds.platform.guardrails.approval_gate import (
    ApprovalGate,
    ApprovalRequest,
    ApprovalStateError,
    ApprovalStatus,
    GuardedAction,
)
from ombuds.platform.guardrails.executing_store import ExecutingApprovalStore

_PAYLOAD: dict[str, JsonValue] = {"claim_id": "c-1", "amount_eur": 250}


class _Recorder:
    def __init__(self, fail_times: int = 0) -> None:
        self.executed: list[str] = []
        self.fail_times = fail_times

    def __call__(self, request: ApprovalRequest) -> None:
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("downstream unavailable")
        self.executed.append(request.id)


def _store(recorder: _Recorder) -> tuple[ExecutingApprovalStore, ApprovalGate]:
    gate = ApprovalGate()
    return ExecutingApprovalStore(gate, {action: recorder for action in GuardedAction}), gate


def test_submitting_executes_nothing() -> None:
    recorder = _Recorder()
    store, _ = _store(recorder)

    store.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    assert recorder.executed == []


def test_approving_runs_the_executor_once_and_returns_the_executed_request() -> None:
    recorder = _Recorder()
    store, _ = _store(recorder)
    request = store.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    result = store.approve(request.id, "alice")

    assert recorder.executed == [request.id]
    assert result.status is ApprovalStatus.EXECUTED
    assert result.approver == "alice"


def test_a_second_approval_raises_and_does_not_execute_again() -> None:
    recorder = _Recorder()
    store, _ = _store(recorder)
    request = store.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)
    store.approve(request.id, "alice")

    with pytest.raises(ApprovalStateError):
        store.approve(request.id, "bob")
    with pytest.raises(ApprovalStateError):
        store.claim_for_execution(request.id)

    assert recorder.executed == [request.id]


def test_denying_executes_nothing() -> None:
    recorder = _Recorder()
    store, _ = _store(recorder)
    request = store.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    store.deny(request.id, "alice")

    assert recorder.executed == []


def test_a_failed_executor_leaves_the_request_approved_and_recoverable() -> None:
    recorder = _Recorder(fail_times=1)
    store, gate = _store(recorder)
    request = store.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    with pytest.raises(RuntimeError):
        store.approve(request.id, "alice")
    assert gate.get(request.id).status is ApprovalStatus.APPROVED

    recovered = store.execute_approved(request.id)

    assert recovered.status is ApprovalStatus.EXECUTED
    assert recorder.executed == [request.id]


def test_execute_approved_refuses_a_request_that_is_not_approved() -> None:
    store, _ = _store(_Recorder())
    request = store.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    with pytest.raises(ApprovalStateError):
        store.execute_approved(request.id)


def test_every_guarded_action_needs_an_executor() -> None:
    with pytest.raises(ValueError, match="issue_payment"):
        ExecutingApprovalStore(ApprovalGate(), {GuardedAction.LOG_CLAIM: _Recorder()})
