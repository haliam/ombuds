"""HTTP surface for the human-approval gate: list pending requests, approve or deny one.

Feature-agnostic (mirrors `approval_gate.py` itself) — mounted directly by the composition root
(`api_app.py`), not by a feature's `api/routes.py`.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ombuds.platform.guardrails.approval_gate import (
    ApprovalNotFoundError,
    ApprovalRequest,
    approve_request,
    deny_request,
    list_pending_approvals,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    """Body for approving or denying a pending request."""

    model_config = ConfigDict(frozen=True)

    approver: str = Field(min_length=1)
    note: str | None = None


@router.get("", response_model=tuple[ApprovalRequest, ...])
def list_pending() -> tuple[ApprovalRequest, ...]:
    """List every request still awaiting a human decision."""
    return list_pending_approvals()


@router.post("/{request_id}/approve", response_model=ApprovalRequest)
def approve(request_id: str, body: ApprovalDecisionRequest) -> ApprovalRequest:
    """Approve a pending request. The tool call it gates isn't retried automatically — the caller (or
    the next agent turn) re-invokes the tool, which then sees the approved decision."""
    try:
        return approve_request(request_id, body.approver, body.note)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{request_id}/deny", response_model=ApprovalRequest)
def deny(request_id: str, body: ApprovalDecisionRequest) -> ApprovalRequest:
    """Deny a pending request."""
    try:
        return deny_request(request_id, body.approver, body.note)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
