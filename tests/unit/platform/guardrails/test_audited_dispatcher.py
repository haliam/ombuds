from collections.abc import Sequence

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult
from ombuds.platform.guardrails.audit_log import AuditKind
from ombuds.platform.guardrails.audited_dispatcher import MAX_RESULT_CHARS, AuditedDispatcher
from tests.unit.platform.guardrails.audit_fakes import RecordingAuditLog


class _Dispatcher:
    def __init__(self, results: dict[str, ToolResult]) -> None:
        self._results = results

    def definitions(self) -> Sequence[ToolDefinition]:
        return []

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        return [self._results[call.id] for call in calls]


def _ok(call_id: str, content: str = "{}") -> ToolResult:
    return ToolResult(call_id=call_id, name="check_eligibility", content=content)


def test_every_call_in_a_batch_gets_one_tool_call_event_in_order() -> None:
    audit = RecordingAuditLog()
    calls = [
        ToolCall(id="1", name="search_kb", arguments={"query": "delay"}),
        ToolCall(id="2", name="log_claim", arguments={"claim_id": "c-1"}),
    ]
    results = [_ok("1"), ToolResult(call_id="2", name="log_claim", content="denied", is_error=True)]

    returned = AuditedDispatcher(_Dispatcher({r.call_id: r for r in results}), audit).dispatch_all(calls)

    assert returned == results
    assert [(e.kind, e.subject, e.outcome, e.claim_id) for e in audit.events] == [
        (AuditKind.TOOL_CALL, "search_kb", "ok", None),
        (AuditKind.TOOL_CALL, "log_claim", "error", "c-1"),
    ]


def test_arguments_and_results_are_redacted_before_being_recorded() -> None:
    audit = RecordingAuditLog()
    call = ToolCall(id="1", name="search_kb", arguments={"query": "jane@example.com"})

    AuditedDispatcher(_Dispatcher({"1": _ok("1", "contact jane@example.com")}), audit).dispatch_all([call])

    assert audit.events[0].detail == {
        "call_id": "1",
        "arguments": {"query": "[EMAIL]"},
        "result": "contact [EMAIL]",
    }


def test_a_long_result_is_truncated() -> None:
    audit = RecordingAuditLog()
    call = ToolCall(id="1", name="search_kb", arguments={})

    AuditedDispatcher(_Dispatcher({"1": _ok("1", "x" * (MAX_RESULT_CHARS + 500))}), audit).dispatch_all([call])

    assert audit.events[0].detail["result"] == "x" * MAX_RESULT_CHARS
