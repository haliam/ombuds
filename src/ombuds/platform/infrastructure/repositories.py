"""Postgres-backed repositories: the durable, cross-process counterparts of the in-memory stores.

`PostgresApprovalStore` implements `ApprovalStore` (ADR-0009): dedup is `INSERT ... ON CONFLICT` on the
`(action, payload_key)` unique constraint and every status change is a compare-and-set `UPDATE ... WHERE
status = ...`, so two processes racing on the same request can't both win.
"""

from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from pydantic import JsonValue

from ombuds.platform.guardrails.approval_gate import (
    ApprovalNotFoundError,
    ApprovalRequest,
    ApprovalStateError,
    ApprovalStatus,
    GuardedAction,
    dedup_key,
)
from ombuds.platform.infrastructure.postgres import Pool

_APPROVAL_COLUMNS = "id, action, payload, status, approver, note"


def _to_request(row: Mapping[str, Any]) -> ApprovalRequest:
    return ApprovalRequest(
        id=row["id"],
        action=GuardedAction(row["action"]),
        payload=row["payload"],
        status=ApprovalStatus(row["status"]),
        approver=row["approver"],
        note=row["note"],
    )


class PostgresApprovalStore:
    """`ApprovalStore` over the `approval_requests` table."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def submit(self, action: GuardedAction, payload: Mapping[str, JsonValue]) -> ApprovalRequest:
        """Create a `PENDING` request for `action`/`payload`, or return the existing one in its current state."""
        if not payload:
            raise ValueError("an approval request needs a non-empty payload describing exactly what is approved")
        _, payload_key = dedup_key(action, payload)
        with self._pool.connection() as conn:
            row = conn.execute(
                f"INSERT INTO approval_requests (action, payload, payload_key) VALUES (%s, %s, %s) "
                f"ON CONFLICT (action, payload_key) DO NOTHING RETURNING {_APPROVAL_COLUMNS}".encode(),
                (action.value, Jsonb(dict(payload)), payload_key),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    f"SELECT {_APPROVAL_COLUMNS} FROM approval_requests "
                    f"WHERE action = %s AND payload_key = %s".encode(),
                    (action.value, payload_key),
                ).fetchone()
        assert row is not None  # the conflicting row was committed by the winner, so the SELECT finds it
        return _to_request(row)

    def list_pending(self) -> tuple[ApprovalRequest, ...]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_APPROVAL_COLUMNS} FROM approval_requests "
                f"WHERE status = 'pending' ORDER BY created_at".encode()
            ).fetchall()
        return tuple(_to_request(row) for row in rows)

    def get(self, request_id: str) -> ApprovalRequest:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_APPROVAL_COLUMNS} FROM approval_requests WHERE id = %s".encode(), (request_id,)
            ).fetchone()
        if row is None:
            raise ApprovalNotFoundError(f"no approval request with id {request_id}")
        return _to_request(row)

    def approve(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        """Approve a `PENDING` request. Approving never executes anything by itself — see `claim_for_execution`."""
        return self._transition(request_id, ApprovalStatus.PENDING, ApprovalStatus.APPROVED, (approver, note))

    def deny(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        """Deny a `PENDING` request. Terminal: a denied payload can't be re-approved, only re-submitted changed."""
        return self._transition(request_id, ApprovalStatus.PENDING, ApprovalStatus.DENIED, (approver, note))

    def claim_for_execution(self, request_id: str) -> ApprovalRequest:
        """Atomically move an `APPROVED` request to `EXECUTED`; exactly one concurrent caller succeeds."""
        return self._transition(request_id, ApprovalStatus.APPROVED, ApprovalStatus.EXECUTED)

    def _transition(
        self,
        request_id: str,
        from_status: ApprovalStatus,
        to_status: ApprovalStatus,
        review: tuple[str, str | None] | None = None,
    ) -> ApprovalRequest:
        with self._pool.connection() as conn:
            if review is None:
                row = conn.execute(
                    f"UPDATE approval_requests SET status = %s, updated_at = now() "
                    f"WHERE id = %s AND status = %s RETURNING {_APPROVAL_COLUMNS}".encode(),
                    (to_status.value, request_id, from_status.value),
                ).fetchone()
            else:
                row = conn.execute(
                    f"UPDATE approval_requests SET status = %s, approver = %s, note = %s, updated_at = now() "
                    f"WHERE id = %s AND status = %s RETURNING {_APPROVAL_COLUMNS}".encode(),
                    (to_status.value, review[0], review[1], request_id, from_status.value),
                ).fetchone()
            if row is not None:
                return _to_request(row)
            current = conn.execute("SELECT status FROM approval_requests WHERE id = %s", (request_id,)).fetchone()
        if current is None:
            raise ApprovalNotFoundError(f"no approval request with id {request_id}")
        raise ApprovalStateError(
            f"approval request {request_id} is {current['status']}, not {from_status}; cannot mark it {to_status}"
        )


class PostgresClaimantFactsRepository:
    """Per-claimant fact dicts in `long_term_memory`.

    Feature-agnostic on purpose (`platform/` can't import `features/`): the claims-triage memory store
    adapts this to its `LongTermMemoryStore` protocol.
    """

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def load(self, claimant_id: str) -> dict[str, str]:
        """Return the claimant's stored facts, or an empty dict if there are none."""
        with self._pool.connection() as conn:
            row = conn.execute("SELECT facts FROM long_term_memory WHERE claimant_id = %s", (claimant_id,)).fetchone()
        return dict(row["facts"]) if row else {}

    def save(self, claimant_id: str, facts: Mapping[str, str]) -> None:
        """Replace the claimant's stored facts with `facts`."""
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO long_term_memory (claimant_id, facts) VALUES (%s, %s) "
                "ON CONFLICT (claimant_id) DO UPDATE SET facts = EXCLUDED.facts, updated_at = now()",
                (claimant_id, Jsonb(dict(facts))),
            )
