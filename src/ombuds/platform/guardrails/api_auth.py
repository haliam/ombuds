"""Bearer-token authentication for the HTTP API (ADR-0019): one credential for triage, another for approve/deny.

Each router attaches the dependency it needs (`require_triage_token` or `require_approver_token`) in its own
`APIRouter(dependencies=[...])`, so the docs pages and `/openapi.json` stay public. Everything fails closed: a token
that is unset, or set to the same value as the other one, makes the endpoint answer 503 rather than let anyone in.
"""

import logging
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from ombuds import config

logger = logging.getLogger(__name__)

_UNAUTHENTICATED = {"WWW-Authenticate": "Bearer"}


def _bearer_token(request: Request) -> str:
    """The token from `Authorization: Bearer <token>`, or 401 if the header is missing or not a bearer one."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="missing bearer token", headers=_UNAUTHENTICATED)
    return token.strip()


def _matches(presented: str, expected: str) -> bool:
    return secrets.compare_digest(presented.encode(), expected.encode())


def _credentials(role: str) -> config.ApiAuth:
    """The configured credentials, or 503 if they cannot safely tell the two roles apart."""
    auth = config.api_auth()
    if not auth.triage_token or not auth.approver_token or not auth.approver:
        logger.error(
            "API authentication is not configured: set OMBUDS_TRIAGE_TOKEN, OMBUDS_APPROVER_TOKEN, OMBUDS_APPROVER"
        )
        raise HTTPException(status_code=503, detail="API authentication is not configured")
    if _matches(auth.triage_token, auth.approver_token):
        logger.error("OMBUDS_TRIAGE_TOKEN and OMBUDS_APPROVER_TOKEN are the same; refusing %s requests", role)
        raise HTTPException(status_code=503, detail="API authentication is misconfigured")
    return auth


def _check(request: Request, role: str, own: str, other: str) -> None:
    """Pass if the bearer token equals `own`; 403 if it is the other role's token, 401 for anything else."""
    presented = _bearer_token(request)
    if _matches(presented, own):
        return
    if _matches(presented, other):
        raise HTTPException(status_code=403, detail=f"this token cannot be used for {role} endpoints")
    raise HTTPException(status_code=401, detail="invalid bearer token", headers=_UNAUTHENTICATED)


def require_triage_token(request: Request) -> None:
    """Dependency for the triage endpoints: only the triage token passes."""
    auth = _credentials("triage")
    _check(request, "triage", auth.triage_token, auth.approver_token)


def require_approver_token(request: Request) -> str:
    """Dependency for `/approvals*`: only the approver token passes. Returns the configured approver name.

    The approver recorded on a decision comes from here, never from the request body.
    """
    auth = _credentials("approver")
    _check(request, "approver", auth.approver_token, auth.triage_token)
    return auth.approver


Approver = Annotated[str, Depends(require_approver_token)]
