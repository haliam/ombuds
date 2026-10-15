"""HTTP surface for the human-approval gate: list pending requests, look one up, approve or deny it.

Feature-agnostic (mirrors `approval_gate.py` itself) — mounted directly by the composition root
(`api_app.py`), not by a feature's `api/routes.py`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ombuds.platform.guardrails.approval_gate import (
    ApprovalNotFoundError,
    ApprovalRequest,
    ApprovalStateError,
    ApprovalStore,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


def get_approval_store(request: Request) -> ApprovalStore:
    """The `ApprovalStore` the composition root put on `app.state` (`api_app.create_app`)."""
    store: ApprovalStore = request.app.state.approvals
    return store


Approvals = Annotated[ApprovalStore, Depends(get_approval_store)]


class ApprovalDecisionRequest(BaseModel):
    """Body for approving or denying a pending request."""

    model_config = ConfigDict(frozen=True)

    approver: str = Field(min_length=1)
    note: str | None = None


@router.get("", response_model=tuple[ApprovalRequest, ...])
def list_pending(approvals: Approvals) -> tuple[ApprovalRequest, ...]:
    """List every request still awaiting a human decision, with the exact payload each one would execute."""
    return approvals.list_pending()


@router.get("/{request_id}", response_model=ApprovalRequest)
def get_request(request_id: str, approvals: Approvals) -> ApprovalRequest:
    """Look up one request in any status, e.g. to follow a `request_id` a tool call returned."""
    try:
        return approvals.get(request_id)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{request_id}/approve", response_model=ApprovalRequest)
def approve(request_id: str, body: ApprovalDecisionRequest, approvals: Approvals) -> ApprovalRequest:
    """Approve a pending request. The approved payload is executed at most once, by its executor (ADR-0009)."""
    try:
        return approvals.approve(request_id, body.approver, body.note)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{request_id}/deny", response_model=ApprovalRequest)
def deny(request_id: str, body: ApprovalDecisionRequest, approvals: Approvals) -> ApprovalRequest:
    """Deny a pending request."""
    try:
        return approvals.deny(request_id, body.approver, body.note)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
