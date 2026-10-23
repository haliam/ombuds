from collections.abc import Sequence

from ombuds.features.claims_triage.tools import build_tool_registry, scope_for_agent
from ombuds.features.claims_triage.tools.check_eligibility import CHECK_ELIGIBILITY_TOOL
from ombuds.features.claims_triage.tools.issue_payment import ISSUE_PAYMENT_TOOL
from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL
from ombuds.features.claims_triage.tools.search_kb import SEARCH_KB_TOOL
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult
from ombuds.platform.guardrails.approval_gate import ApprovalGate
from ombuds.platform.guardrails.audit_log import AuditKind
from tests.fakes import InMemoryClaims
from tests.unit.platform.guardrails.audit_fakes import RecordingAuditLog


def test_build_tool_registry_registers_exactly_the_four_claims_triage_tools() -> None:
    registry = build_tool_registry(ApprovalGate(), InMemoryClaims())

    definitions = registry.definitions()

    assert {d.name for d in definitions} == {
        SEARCH_KB_TOOL.name,
        CHECK_ELIGIBILITY_TOOL.name,
        LOG_CLAIM_TOOL.name,
        ISSUE_PAYMENT_TOOL.name,
    }


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []

    def definitions(self) -> Sequence[ToolDefinition]:
        return [SEARCH_KB_TOOL, CHECK_ELIGIBILITY_TOOL, LOG_CLAIM_TOOL, ISSUE_PAYMENT_TOOL]

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        self.calls.extend(calls)
        return [ToolResult(call_id=call.id, name=call.name, content="{}") for call in calls]


def test_scope_for_agent_replaces_a_model_supplied_claim_id() -> None:
    inner = _RecordingDispatcher()

    scope_for_agent(inner, "CLM-SERVER").dispatch_all(
        [ToolCall(id="c1", name=LOG_CLAIM_TOOL.name, arguments={"claim_id": "CLM-FROM-MODEL", "disruption": {}})]
    )

    assert inner.calls[0].arguments == {"claim_id": "CLM-SERVER", "disruption": {}}


def test_scope_for_agent_never_offers_issue_payment() -> None:
    names = {d.name for d in scope_for_agent(_RecordingDispatcher(), "CLM-SERVER").definitions()}

    assert names == {SEARCH_KB_TOOL.name, CHECK_ELIGIBILITY_TOOL.name, LOG_CLAIM_TOOL.name}


def test_scope_for_agent_refuses_a_call_to_a_tool_outside_the_agent_set_without_dispatching_it() -> None:
    inner = _RecordingDispatcher()

    results = scope_for_agent(inner, "CLM-SERVER").dispatch_all(
        [
            ToolCall(id="c1", name=ISSUE_PAYMENT_TOOL.name, arguments={"claim_id": "CLM-SERVER"}),
            ToolCall(id="c2", name=CHECK_ELIGIBILITY_TOOL.name, arguments={}),
        ]
    )

    assert [call.name for call in inner.calls] == [CHECK_ELIGIBILITY_TOOL.name]
    assert [(r.call_id, r.is_error) for r in results] == [("c1", True), ("c2", False)]


def test_scope_for_agent_leaves_other_tools_arguments_untouched() -> None:
    inner = _RecordingDispatcher()
    arguments: dict[str, object] = {"distance_km": 1200}

    scope_for_agent(inner, "CLM-SERVER").dispatch_all(
        [ToolCall(id="c1", name=CHECK_ELIGIBILITY_TOOL.name, arguments=arguments)]
    )

    assert inner.calls[0].arguments == {"distance_km": 1200}


def test_scope_for_agent_audits_a_refused_call_with_redacted_arguments() -> None:
    audit = RecordingAuditLog()

    scope_for_agent(_RecordingDispatcher(), "CLM-SERVER", audit).dispatch_all(
        [
            ToolCall(id="c1", name=ISSUE_PAYMENT_TOOL.name, arguments={"claim_id": "CLM-MODEL", "note": "a@b.com"}),
            ToolCall(id="c2", name=CHECK_ELIGIBILITY_TOOL.name, arguments={}),
        ]
    )

    (event,) = audit.events
    assert (event.kind, event.subject, event.outcome, event.claim_id) == (
        AuditKind.TOOL_REFUSED,
        ISSUE_PAYMENT_TOOL.name,
        "refused",
        "CLM-SERVER",
    )
    assert event.detail["call_id"] == "c1"
    assert event.detail["reason"] == "out_of_scope"
    assert "a@b.com" not in str(event.detail)


def test_scope_for_agent_audits_nothing_when_every_call_is_in_scope() -> None:
    audit = RecordingAuditLog()

    scope_for_agent(_RecordingDispatcher(), "CLM-SERVER", audit).dispatch_all(
        [ToolCall(id="c1", name=CHECK_ELIGIBILITY_TOOL.name, arguments={})]
    )

    assert audit.events == []
