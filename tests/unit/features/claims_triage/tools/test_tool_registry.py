from collections.abc import Sequence

from ombuds.features.claims_triage.tools import bind_to_claim, build_tool_registry
from ombuds.features.claims_triage.tools.check_eligibility import CHECK_ELIGIBILITY_TOOL
from ombuds.features.claims_triage.tools.issue_payment import ISSUE_PAYMENT_TOOL
from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL
from ombuds.features.claims_triage.tools.search_kb import SEARCH_KB_TOOL
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult


def test_build_tool_registry_registers_exactly_the_four_claims_triage_tools() -> None:
    registry = build_tool_registry()

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
        return [CHECK_ELIGIBILITY_TOOL, LOG_CLAIM_TOOL]

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        self.calls.extend(calls)
        return [ToolResult(call_id=call.id, name=call.name, content="{}") for call in calls]


def test_bind_to_claim_replaces_a_model_supplied_claim_id_on_claim_scoped_tools() -> None:
    inner = _RecordingDispatcher()
    bound = bind_to_claim(inner, "CLM-SERVER")

    bound.dispatch_all(
        [
            ToolCall(id="c1", name=LOG_CLAIM_TOOL.name, arguments={"claim_id": "CLM-FROM-MODEL", "disruption": {}}),
            ToolCall(id="c2", name=ISSUE_PAYMENT_TOOL.name, arguments={}),
        ]
    )

    assert [call.arguments["claim_id"] for call in inner.calls] == ["CLM-SERVER", "CLM-SERVER"]
    assert inner.calls[0].arguments["disruption"] == {}


def test_bind_to_claim_leaves_other_tools_arguments_untouched() -> None:
    inner = _RecordingDispatcher()
    arguments: dict[str, object] = {"distance_km": 1200}

    bind_to_claim(inner, "CLM-SERVER").dispatch_all(
        [ToolCall(id="c1", name=CHECK_ELIGIBILITY_TOOL.name, arguments=arguments)]
    )

    assert inner.calls[0].arguments == {"distance_km": 1200}


def test_bind_to_claim_passes_definitions_through() -> None:
    inner = _RecordingDispatcher()

    assert list(bind_to_claim(inner, "CLM-SERVER").definitions()) == list(inner.definitions())
