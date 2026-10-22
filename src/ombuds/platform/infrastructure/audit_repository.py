"""Postgres sink for the audit trail: an append-only `audit_log` table (ADR-0016).

The repository only inserts and reads. Immutability is enforced by triggers in migration 0003, so even a
caller with raw SQL access through this pool cannot rewrite history.
"""

from typing import Any

from psycopg.types.json import Jsonb

from ombuds.platform.guardrails.audit_log import AuditEvent, AuditKind
from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.observability.tracing import current_trace_id

_COLUMNS = "kind, subject, outcome, claim_id, approval_request_id, detail, trace_id"


class PostgresAuditLog:
    """`AuditLog` over the `audit_log` table."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def record(self, event: AuditEvent) -> None:
        """Append `event`, stamped with the active trace id (ADR-0017).

        Raises on a database error: an action must not proceed unaudited.
        """
        with self._pool.connection() as conn:
            conn.execute(
                f"INSERT INTO audit_log ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s)".encode(),
                (
                    event.kind.value,
                    event.subject,
                    event.outcome,
                    event.claim_id,
                    event.approval_request_id,
                    Jsonb(event.detail),
                    event.trace_id or current_trace_id(),
                ),
            )

    def for_claim(self, claim_id: str) -> tuple[AuditEvent, ...]:
        """Every event recorded for `claim_id`, oldest first."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM audit_log WHERE claim_id = %s ORDER BY id".encode(), (claim_id,)
            ).fetchall()
        return tuple(_to_event(row) for row in rows)


def _to_event(row: dict[str, Any]) -> AuditEvent:
    return AuditEvent(
        kind=AuditKind(row["kind"]),
        subject=row["subject"],
        outcome=row["outcome"],
        claim_id=row["claim_id"],
        approval_request_id=row["approval_request_id"],
        detail=row["detail"],
        trace_id=row["trace_id"],
    )
