"""POST /claims/triage"""

from fastapi import APIRouter

from ombuds.features.claims_triage.api.schemas import TriageRequest, TriageResponse
from ombuds.features.claims_triage.application.triage_use_case import run_triage

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest) -> TriageResponse:
    """Run the claims-triage tool-use loop over one claim and return its answer plus every tool call made."""
    result = run_triage(request.claim_text)
    return TriageResponse(answer=result.answer, tool_results=result.tool_results)
