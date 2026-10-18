"""A `ToolDispatcher` wrapper that records every tool call and its outcome in the audit log (ADR-0016).

Sits directly around the registry, inside `GuardedDispatcher` and the agent scoping, so it records what the
tool actually received: PII already redacted and `claim_id` already pinned. The result is stored redacted and
truncated; a failure surfaces as `outcome="error"`, not as a missing row.
"""

from collections.abc import Sequence

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult
from ombuds.platform.ai.tool_loop import ToolDispatcher
from ombuds.platform.guardrails.audit_log import AuditEvent, AuditKind, AuditLog
from ombuds.platform.guardrails.pii_filter import redact, redact_value

MAX_RESULT_CHARS = 2000
"""Cap on the stored result text, so a large `search_kb` answer can't bloat the table."""


class AuditedDispatcher:
    """Delegates to `inner`, then writes one `tool_call` event per call."""

    def __init__(self, inner: ToolDispatcher, audit: AuditLog) -> None:
        self._inner = inner
        self._audit = audit

    def definitions(self) -> Sequence[ToolDefinition]:
        return self._inner.definitions()

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        results = self._inner.dispatch_all(calls)
        for call, result in zip(calls, results, strict=True):
            self._audit.record(_event(call, result))
        return results


def _event(call: ToolCall, result: ToolResult) -> AuditEvent:
    claim_id = call.arguments.get("claim_id")
    arguments = redact_value(call.arguments)
    assert isinstance(arguments, dict)
    return AuditEvent(
        kind=AuditKind.TOOL_CALL,
        subject=call.name,
        outcome="error" if result.is_error else "ok",
        claim_id=claim_id if isinstance(claim_id, str) else None,
        detail={
            "call_id": call.id,
            "arguments": arguments,
            "result": redact(result.content[:MAX_RESULT_CHARS]).text,
        },
    )
