"""HTTP surface for the human-approval gate: list pending requests, look one up, approve or deny it.

Feature-agnostic (mirrors `approval_gate.py` itself) — mounted directly by the composition root
(`api_app.py`), not by a feature's `api/routes.py`.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ombuds.domain.errors import ToolExecutionError
from ombuds.platform.guardrails.approval_gate import (
    ApprovalNotFoundError,
    ApprovalRequest,
    ApprovalStateError,
    ExecutableApprovalStore,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


def get_approval_store(request: Request) -> ExecutableApprovalStore:
    """The `ExecutableApprovalStore` the composition root put on `app.state` (`api_app.create_app`)."""
    store: ExecutableApprovalStore = request.app.state.approvals
    return store


Approvals = Annotated[ExecutableApprovalStore, Depends(get_approval_store)]


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


def _execution_failed(request_id: str, approvals: ExecutableApprovalStore, exc: ToolExecutionError) -> JSONResponse:
    """The executor refused an approved request: it stays `APPROVED`, so say so and point at the retry route."""
    return JSONResponse(
        status_code=502,
        content={
            "detail": f"approved, but executing it failed: {exc}. Fix the cause, then retry with "
            f"POST /approvals/{request_id}/execute",
            "request_id": request_id,
            "status": approvals.get(request_id).status,
        },
    )


@router.post(
    "/{request_id}/approve",
    response_model=ApprovalRequest,
    responses={502: {"description": "Approved, but its executor failed"}},
)
def approve(request_id: str, body: ApprovalDecisionRequest, approvals: Approvals) -> ApprovalRequest | JSONResponse:
    """Approve a pending request. The approved payload is executed at most once, by its executor (ADR-0009).

    If the executor fails the request stays `APPROVED` and the response is a 502 naming it; retry with `/execute`.
    """
    try:
        return approvals.approve(request_id, body.approver, body.note)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ToolExecutionError as exc:
        return _execution_failed(request_id, approvals, exc)
    except Exception:
        logger.exception("executing approved request %s failed unexpectedly", request_id)
        raise


@router.post(
    "/{request_id}/execute",
    response_model=ApprovalRequest,
    responses={502: {"description": "Its executor failed again"}},
)
def execute(request_id: str, approvals: Approvals) -> ApprovalRequest | JSONResponse:
    """Re-run an `APPROVED` request whose executor failed or was interrupted; it ends `EXECUTED`, once (ADR-0009).

    409 for a request in any other status, and nothing is written.
    """
    try:
        return approvals.execute_approved(request_id)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ToolExecutionError as exc:
        return _execution_failed(request_id, approvals, exc)
    except Exception:
        logger.exception("executing approved request %s failed unexpectedly", request_id)
        raise


@router.post("/{request_id}/deny", response_model=ApprovalRequest)
def deny(request_id: str, body: ApprovalDecisionRequest, approvals: Approvals) -> ApprovalRequest:
    """Deny a pending request."""
    try:
        return approvals.deny(request_id, body.approver, body.note)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
