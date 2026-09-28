"""POST /claims/triage and its streaming (SSE) counterpart, POST /claims/triage/stream."""

import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ombuds.features.claims_triage.api.schemas import TriageRequest, TriageResponse
from ombuds.features.claims_triage.application.triage_use_case import run_triage, stream_triage
from ombuds.platform.ai.streaming import StreamEvent, TextDelta, ToolCallDelta, ToolResultEvent, TurnDone

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest) -> TriageResponse:
    """Run the claims-triage tool-use loop over one claim and return its answer plus every tool call made."""
    result = run_triage(request.claim_text)
    return TriageResponse(
        answer=result.answer,
        decision=result.decision,
        tool_results=result.tool_results,
        escalated=result.escalated,
        escalation_reason=result.escalation_reason,
    )


@router.post("/triage/stream")
def triage_stream(request: TriageRequest) -> StreamingResponse:
    """Run the same tool-use loop, streaming each event over Server-Sent Events as it happens."""
    return StreamingResponse(_to_sse(stream_triage(request.claim_text)), media_type="text/event-stream")


def _to_sse(events: Iterator[StreamEvent]) -> Iterator[str]:
    """Format each `StreamEvent` as one `data: <json>\\n\\n` SSE frame."""
    for event in events:
        yield f"data: {json.dumps(_event_payload(event))}\n\n"


def _event_payload(event: StreamEvent) -> dict[str, object]:
    if isinstance(event, TextDelta):
        return {"type": "text_delta", "text": event.text}
    if isinstance(event, ToolCallDelta):
        return {"type": "tool_call", "call": event.call.model_dump()}
    if isinstance(event, ToolResultEvent):
        return {"type": "tool_result", "result": event.result.model_dump()}
    if isinstance(event, TurnDone):
        return {
            "type": "turn_done",
            "text": event.text,
            "stop_reason": event.stop_reason,
            "tool_calls": [call.model_dump() for call in event.tool_calls],
        }
    raise TypeError(f"unhandled stream event: {event!r}")
