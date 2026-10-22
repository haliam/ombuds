"""Build the claims-triage runtime over one Postgres pool: the approval store and the tool registry.

Shared by the composition roots (`api_app.py`, the MCP server) so the API process and the MCP subprocess
wire approvals, executors and tools identically.
"""

from collections.abc import Callable
from dataclasses import dataclass

from ombuds.features.claims_triage.application.executors import build_executors
from ombuds.features.claims_triage.rag.retriever import Retriever, default_retriever
from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.ai.tool_loop import ToolDispatcher
from ombuds.platform.guardrails.approval_gate import ExecutableApprovalStore
from ombuds.platform.guardrails.audited_dispatcher import AuditedDispatcher
from ombuds.platform.guardrails.audited_store import AuditedApprovalStore
from ombuds.platform.guardrails.executing_store import ExecutingApprovalStore
from ombuds.platform.guardrails.policy_checked_store import PolicyCheckedApprovalStore
from ombuds.platform.guardrails.policy_engine import PolicyEngine
from ombuds.platform.infrastructure.audit_repository import PostgresAuditLog
from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.infrastructure.repositories import (
    PostgresApprovalStore,
    PostgresClaimRepository,
    PostgresPaymentRepository,
)
from ombuds.platform.observability.traced_dispatcher import TracedDispatcher


@dataclass(frozen=True)
class ClaimsTriageRuntime:
    """What a process needs to serve claims triage: where approvals go, and the tools that submit to them."""

    approvals: ExecutableApprovalStore
    registry: ToolDispatcher


def build_runtime(
    pool: Pool,
    policy_engine: PolicyEngine,
    payout_limit_eur: int,
    retriever_factory: Callable[[], Retriever] = default_retriever,
) -> ClaimsTriageRuntime:
    """Approvals backed by Postgres, executed against `claims`/`payments`, plus the full tool registry.

    Submissions are checked by `policy_engine` first (ADR-0015); a payout above `payout_limit_eur` is denied.
    Required, with no default, so a composition root can't forget the guardrail. Every tool call, policy
    verdict and approval transition is written to the audit log (ADR-0016), and every tool call is a span (ADR-0017).

    `retriever_factory` is for tests that search over fakes; see `build_tool_registry`.
    """
    claims = PostgresClaimRepository(pool)
    audit = PostgresAuditLog(pool)
    executing = ExecutingApprovalStore(
        AuditedApprovalStore(PostgresApprovalStore(pool), audit),
        build_executors(claims, PostgresPaymentRepository(pool)),
    )
    approvals = PolicyCheckedApprovalStore(executing, policy_engine, {"max_payout_eur": payout_limit_eur}, audit)
    registry = TracedDispatcher(AuditedDispatcher(build_tool_registry(approvals, claims, retriever_factory), audit))
    return ClaimsTriageRuntime(approvals=approvals, registry=registry)
