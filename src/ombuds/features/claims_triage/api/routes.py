"""POST /claims/triage and its streaming (SSE) counterpart, POST /claims/triage/stream.

Both run the same graph and return the same verified outcome; the stream only adds progress frames before it.
"""

import json
import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ombuds.features.claims_triage.api.schemas import TriageRequest, TriageResponse
from ombuds.features.claims_triage.application.triage_use_case import (
    TriageCompleted,
    TriageResult,
    TriageStreamEvent,
    run_triage,
    stream_triage,
)
from ombuds.platform.ai.budget import BudgetExceededError
from ombuds.platform.ai.providers.base import ProviderUnavailableError
from ombuds.platform.ai.streaming import ToolCallDelta, ToolResultEvent
from ombuds.platform.ai.tool_loop import ToolDispatcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claims", tags=["claims"])


def get_registry(request: Request) -> ToolDispatcher:
    """The tool catalogue the composition root put on `app.state` (`api_app.create_app`)."""
    registry: ToolDispatcher = request.app.state.registry
    return registry


Registry = Annotated[ToolDispatcher, Depends(get_registry)]


@router.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest, registry: Registry) -> TriageResponse:
    """Run the claims-triage tool-use loop over one claim and return its answer plus every tool call made.

    The `claim_id` is always issued by the server (ADR-0009) and returned so the caller can follow up on it.
    """
    return _to_response(run_triage(request.claim_text, registry=registry))


@router.post("/triage/stream")
def triage_stream(request: TriageRequest, registry: Registry) -> StreamingResponse:
    """Run the same triage as `/triage`, streaming progress over Server-Sent Events (ADR-0007).

    Frames, one JSON object each: `tool_call` and `tool_result` as they happen, then exactly one `final`
    carrying the same fields as `/triage`'s response — or an `error` frame if the LLM provider is unavailable.
    Unverified model text is never streamed (see `stream_triage`).
    """
    events = stream_triage(request.claim_text, registry=registry)
    return StreamingResponse(_to_sse(events), media_type="text/event-stream")


def _to_response(result: TriageResult) -> TriageResponse:
    return TriageResponse(
        claim_id=result.claim_id,
        answer=result.answer,
        decision=result.decision,
        tool_results=result.tool_results,
        escalated=result.escalated,
        escalation_reason=result.escalation_reason,
    )


def _to_sse(events: Iterator[TriageStreamEvent]) -> Iterator[str]:
    """Format each event as one `data: <json>\\n\\n` SSE frame, ending in an `error` frame if the provider fails.

    Only `ProviderUnavailableError` and `BudgetExceededError` become error frames: once streaming has started the HTTP status is
    already 200, so this is the only way to tell the client. Anything else is a bug and propagates.
    """
    try:
        for event in events:
            yield _frame(_event_payload(event))
    except ProviderUnavailableError:
        logger.exception("triage stream aborted: LLM provider unavailable")
        yield _frame({"type": "error", "detail": "the LLM provider is unavailable; please retry later"})
    except BudgetExceededError as exc:
        logger.warning("triage stream refused: %s", exc)
        yield _frame({"type": "error", "detail": str(exc)})


def _frame(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _event_payload(event: TriageStreamEvent) -> dict[str, object]:
    if isinstance(event, ToolCallDelta):
        return {"type": "tool_call", "call": event.call.model_dump()}
    if isinstance(event, ToolResultEvent):
        return {"type": "tool_result", "result": event.result.model_dump()}
    if isinstance(event, TriageCompleted):
        return {"type": "final", **_to_response(event.result).model_dump(mode="json")}
    raise TypeError(f"unhandled stream event: {event!r}")
