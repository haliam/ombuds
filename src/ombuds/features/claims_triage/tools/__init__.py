"""The claims-triage tool catalogue: every claims-triage tool, wired to its handler.

`build_tool_registry()` is the one place that knows the full set of claims-triage tools and how to
adapt each `ToolCall`'s validated arguments into its handler's call. `application/triage_use_case.py`
narrows it to the agent's tools for one run via `scope_for_agent()`; `platform/mcp/tool_bindings.py`
(a composition root's concern — see ADR-0003) wraps whatever `ToolRegistry` it's given for MCP
exposure without needing to know this feature exists.
"""

from collections.abc import Callable, Sequence

from pydantic import BaseModel

from ombuds.features.claims_triage.rag.retriever import Retriever, default_retriever
from ombuds.features.claims_triage.tools.check_eligibility import CHECK_ELIGIBILITY_TOOL
from ombuds.features.claims_triage.tools.check_eligibility import check_eligibility as _check_eligibility_impl
from ombuds.features.claims_triage.tools.issue_payment import ISSUE_PAYMENT_TOOL, ClaimLookup, IssuePaymentArgs
from ombuds.features.claims_triage.tools.issue_payment import issue_payment as _issue_payment_impl
from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL, LogClaimArgs
from ombuds.features.claims_triage.tools.log_claim import log_claim as _log_claim_impl
from ombuds.features.claims_triage.tools.search_kb import SEARCH_KB_TOOL, SearchKbArgs
from ombuds.features.claims_triage.tools.search_kb import search_kb as _search_kb_impl
from ombuds.features.claims_triage.verticals.airline.evidence_schema import FlightDisruption
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult
from ombuds.platform.ai.tool_loop import ToolDispatcher, ToolRegistry
from ombuds.platform.guardrails.approval_gate import ApprovalStore

# Imported with a distinct name (`as _..._impl`) rather than the tool's own name, deliberately: binding
# a name identical to the submodule (`check_eligibility`/`log_claim`) here in this package's namespace
# would shadow that submodule as an attribute of `ombuds.features.claims_triage.tools`, which breaks
# `import ombuds.features.claims_triage.tools.log_claim as ...` for anyone importing the submodule itself
# (e.g. to monkeypatch it in a test).


def _check_eligibility(args: BaseModel) -> BaseModel:
    if not isinstance(args, FlightDisruption):
        raise TypeError(f"check_eligibility expected FlightDisruption, got {type(args).__name__}")
    return _check_eligibility_impl(args)


AGENT_TOOL_NAMES = frozenset({SEARCH_KB_TOOL.name, CHECK_ELIGIBILITY_TOOL.name, LOG_CLAIM_TOOL.name})
CLAIM_SCOPED_TOOLS = frozenset({LOG_CLAIM_TOOL.name, ISSUE_PAYMENT_TOOL.name})


class _AgentScopedDispatcher:
    """A `ToolDispatcher` limited to the triage agent's tools, with claim-scoped calls pinned to one claim."""

    def __init__(self, inner: ToolDispatcher, claim_id: str) -> None:
        self._inner = inner
        self._claim_id = claim_id

    def definitions(self) -> Sequence[ToolDefinition]:
        return [definition for definition in self._inner.definitions() if definition.name in AGENT_TOOL_NAMES]

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        allowed = [self._bind(call) for call in calls if call.name in AGENT_TOOL_NAMES]
        dispatched = iter(self._inner.dispatch_all(allowed))
        return [
            next(dispatched)
            if call.name in AGENT_TOOL_NAMES
            else ToolResult(call_id=call.id, name=call.name, content=f"unknown tool: {call.name}", is_error=True)
            for call in calls
        ]

    def _bind(self, call: ToolCall) -> ToolCall:
        if call.name not in CLAIM_SCOPED_TOOLS:
            return call
        return call.model_copy(update={"arguments": {**call.arguments, "claim_id": self._claim_id}})


def scope_for_agent(dispatcher: ToolDispatcher, claim_id: str) -> ToolDispatcher:
    """Wrap `dispatcher` into exactly what the triage agent may do in one run (ADR-0009).

    - Only `AGENT_TOOL_NAMES` are offered, and a call to any other tool comes back as an error result
      without being dispatched: `issue_payment` stays available over MCP for operators, never to the agent.
    - Any `claim_id` the model passes to a claim-scoped tool is replaced with the run's server-issued
      `claim_id`, the key approvals and, from W3, persistence dedupe on.

    Works over any `ToolDispatcher`, so the in-process registry and the MCP client path are scoped the same way.
    """
    return _AgentScopedDispatcher(dispatcher, claim_id)


def build_tool_registry(
    approvals: ApprovalStore, claims: ClaimLookup, retriever_factory: Callable[[], Retriever] = default_retriever
) -> ToolRegistry:
    """Build a `ToolRegistry` with every claims-triage tool: `search_kb`, `check_eligibility`, `log_claim`
    and `issue_payment`.

    `approvals` is the store the state-changing tools submit to and `claims` the logged claims
    `issue_payment` checks against; the composition root (`api_app.py`, the MCP server) chooses both, so no
    tool reaches for a global.

    `retriever_factory` is only called when `search_kb` actually runs, so building the registry needs no
    database or API key; tests pass a factory returning a retriever over fakes.
    """

    def _search_kb(args: BaseModel) -> BaseModel:
        if not isinstance(args, SearchKbArgs):
            raise TypeError(f"search_kb expected SearchKbArgs, got {type(args).__name__}")
        return _search_kb_impl(args, retriever_factory())

    def _log_claim(args: BaseModel) -> BaseModel:
        if not isinstance(args, LogClaimArgs):
            raise TypeError(f"log_claim expected LogClaimArgs, got {type(args).__name__}")
        return _log_claim_impl(args, approvals)

    def _issue_payment(args: BaseModel) -> BaseModel:
        if not isinstance(args, IssuePaymentArgs):
            raise TypeError(f"issue_payment expected IssuePaymentArgs, got {type(args).__name__}")
        return _issue_payment_impl(args, approvals, claims)

    registry = ToolRegistry()
    registry.register(SEARCH_KB_TOOL, _search_kb)
    registry.register(CHECK_ELIGIBILITY_TOOL, _check_eligibility)
    registry.register(LOG_CLAIM_TOOL, _log_claim)
    registry.register(ISSUE_PAYMENT_TOOL, _issue_payment)
    return registry
