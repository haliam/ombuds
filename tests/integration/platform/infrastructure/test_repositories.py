"""PostgresApprovalStore and PostgresClaimantFactsRepository against a real database."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import JsonValue

from ombuds.platform.guardrails.approval_gate import (
    ApprovalNotFoundError,
    ApprovalStateError,
    ApprovalStatus,
    GuardedAction,
)
from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.infrastructure.repositories import PostgresApprovalStore, PostgresClaimantFactsRepository

PAYLOAD: dict[str, JsonValue] = {"claim_id": "c-1", "eligible": True, "compensation_eur": 400}


def test_submit_is_idempotent_on_action_and_payload(pool: Pool) -> None:
    store = PostgresApprovalStore(pool)

    first = store.submit(GuardedAction.LOG_CLAIM, PAYLOAD)
    again = store.submit(GuardedAction.LOG_CLAIM, dict(reversed(PAYLOAD.items())))

    assert again.id == first.id
    assert first.status is ApprovalStatus.PENDING
    assert store.list_pending() == (first,)


def test_changed_payload_or_action_is_a_new_request(pool: Pool) -> None:
    store = PostgresApprovalStore(pool)

    base = store.submit(GuardedAction.LOG_CLAIM, PAYLOAD)
    other_payload = store.submit(GuardedAction.LOG_CLAIM, {**PAYLOAD, "compensation_eur": 250})
    other_action = store.submit(GuardedAction.ISSUE_PAYMENT, PAYLOAD)

    assert len({base.id, other_payload.id, other_action.id}) == 3


def test_approve_then_claim_for_execution_happy_path(pool: Pool) -> None:
    store = PostgresApprovalStore(pool)
    request = store.submit(GuardedAction.ISSUE_PAYMENT, PAYLOAD)

    approved = store.approve(request.id, "alice", "looks right")
    executed = store.claim_for_execution(request.id)

    assert (approved.status, approved.approver, approved.note) == (ApprovalStatus.APPROVED, "alice", "looks right")
    assert executed.status is ApprovalStatus.EXECUTED
    assert store.get(request.id).status is ApprovalStatus.EXECUTED


def test_invalid_transitions_raise_state_error(pool: Pool) -> None:
    store = PostgresApprovalStore(pool)
    request = store.submit(GuardedAction.LOG_CLAIM, PAYLOAD)

    with pytest.raises(ApprovalStateError):
        store.claim_for_execution(request.id)  # not approved yet
    store.deny(request.id, "bob")
    with pytest.raises(ApprovalStateError):
        store.approve(request.id, "bob")  # denied is terminal


def test_unknown_id_raises_not_found(pool: Pool) -> None:
    store = PostgresApprovalStore(pool)

    with pytest.raises(ApprovalNotFoundError):
        store.get("nope")
    with pytest.raises(ApprovalNotFoundError):
        store.approve("nope", "alice")


def test_empty_payload_is_rejected(pool: Pool) -> None:
    with pytest.raises(ValueError):
        PostgresApprovalStore(pool).submit(GuardedAction.LOG_CLAIM, {})


def test_exactly_one_concurrent_caller_wins_claim_for_execution(pool: Pool) -> None:
    store = PostgresApprovalStore(pool)
    request = store.submit(GuardedAction.ISSUE_PAYMENT, PAYLOAD)
    store.approve(request.id, "alice")

    def attempt() -> bool:
        try:
            store.claim_for_execution(request.id)
        except ApprovalStateError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: attempt(), range(8)))

    assert results.count(True) == 1


def test_concurrent_submits_of_same_payload_create_one_request(pool: Pool) -> None:
    store = PostgresApprovalStore(pool)

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = {r.id for r in executor.map(lambda _: store.submit(GuardedAction.LOG_CLAIM, PAYLOAD), range(8))}

    assert len(ids) == 1


def test_claimant_facts_round_trip_and_replace(pool: Pool) -> None:
    repo = PostgresClaimantFactsRepository(pool)

    assert repo.load("claimant-1") == {}
    repo.save("claimant-1", {"last_claim": "approved"})
    repo.save("claimant-1", {"last_claim": "denied", "flights": "2"})

    assert repo.load("claimant-1") == {"last_claim": "denied", "flights": "2"}
    assert repo.load("claimant-2") == {}
