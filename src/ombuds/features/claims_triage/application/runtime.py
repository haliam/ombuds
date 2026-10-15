"""Build the claims-triage runtime over one Postgres pool: the approval store and the tool registry.

Shared by the composition roots (`api_app.py`, the MCP server) so the API process and the MCP subprocess
wire approvals, executors and tools identically.
"""

from collections.abc import Callable
from dataclasses import dataclass

from ombuds.features.claims_triage.application.executors import build_executors
from ombuds.features.claims_triage.rag.retriever import Retriever, default_retriever
from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.ai.tool_loop import ToolRegistry
from ombuds.platform.guardrails.approval_gate import ApprovalStore
from ombuds.platform.guardrails.executing_store import ExecutingApprovalStore
from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.infrastructure.repositories import (
    PostgresApprovalStore,
    PostgresClaimRepository,
    PostgresPaymentRepository,
)


@dataclass(frozen=True)
class ClaimsTriageRuntime:
    """What a process needs to serve claims triage: where approvals go, and the tools that submit to them."""

    approvals: ApprovalStore
    registry: ToolRegistry


def build_runtime(pool: Pool, retriever_factory: Callable[[], Retriever] = default_retriever) -> ClaimsTriageRuntime:
    """Approvals backed by Postgres, executed against `claims`/`payments`, plus the full tool registry.

    `retriever_factory` is for tests that search over fakes; see `build_tool_registry`.
    """
    claims = PostgresClaimRepository(pool)
    approvals = ExecutingApprovalStore(
        PostgresApprovalStore(pool), build_executors(claims, PostgresPaymentRepository(pool))
    )
    return ClaimsTriageRuntime(approvals=approvals, registry=build_tool_registry(approvals, claims, retriever_factory))
