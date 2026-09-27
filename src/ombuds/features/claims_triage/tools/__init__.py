"""The claims-triage tool catalogue: every tool the agent can call, wired to its handler.

`build_tool_registry()` is the one place that knows the full set of claims-triage tools and how to
adapt each `ToolCall`'s validated arguments into its handler's call. `application/triage_use_case.py`
uses it directly; `platform/mcp/tool_bindings.py` (a composition root's concern — see ADR-0003) wraps
whatever `ToolRegistry` it's given for MCP exposure without needing to know this feature exists.
"""

from pydantic import BaseModel

from ombuds.features.claims_triage.tools.check_eligibility import CHECK_ELIGIBILITY_TOOL
from ombuds.features.claims_triage.tools.check_eligibility import check_eligibility as _check_eligibility_impl
from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL, LogClaimArgs
from ombuds.features.claims_triage.tools.log_claim import log_claim as _log_claim_impl
from ombuds.features.claims_triage.verticals.airline.evidence_schema import FlightDisruption
from ombuds.platform.ai.tool_loop import ToolRegistry

# Imported with a distinct name (`as _..._impl`) rather than the tool's own name, deliberately: binding
# a name identical to the submodule (`check_eligibility`/`log_claim`) here in this package's namespace
# would shadow that submodule as an attribute of `ombuds.features.claims_triage.tools`, which breaks
# `import ombuds.features.claims_triage.tools.log_claim as ...` for anyone importing the submodule itself
# (e.g. to monkeypatch it in a test).


def _check_eligibility(args: BaseModel) -> BaseModel:
    if not isinstance(args, FlightDisruption):
        raise TypeError(f"check_eligibility expected FlightDisruption, got {type(args).__name__}")
    return _check_eligibility_impl(args)


def _log_claim(args: BaseModel) -> BaseModel:
    if not isinstance(args, LogClaimArgs):
        raise TypeError(f"log_claim expected LogClaimArgs, got {type(args).__name__}")
    return _log_claim_impl(args)


def build_tool_registry() -> ToolRegistry:
    """Build a `ToolRegistry` with every claims-triage tool: `check_eligibility` and `log_claim`."""
    registry = ToolRegistry()
    registry.register(CHECK_ELIGIBILITY_TOOL, _check_eligibility)
    registry.register(LOG_CLAIM_TOOL, _log_claim)
    return registry
