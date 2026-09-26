from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ombuds.api_app import app
from ombuds.features.claims_triage.api import routes
from ombuds.features.claims_triage.application.decision import TriageDecision
from ombuds.features.claims_triage.application.triage_use_case import TriageResult
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolResult
from ombuds.platform.ai.streaming import StreamEvent, TextDelta, ToolCallDelta, ToolResultEvent, TurnDone

client = TestClient(app)


def test_triage_endpoint_returns_the_use_case_result(monkeypatch) -> None:
    def _fake_run_triage(claim_text: str, *, provider=None) -> TriageResult:
        assert claim_text == "My flight was cancelled."
        return TriageResult(answer="Please provide your flight details.", decision=None, tool_results=())

    monkeypatch.setattr(routes, "run_triage", _fake_run_triage)

    response = client.post("/claims/triage", json={"claim_text": "My flight was cancelled."})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Please provide your flight details.",
        "decision": None,
        "tool_results": [],
    }


def test_triage_endpoint_rejects_an_empty_claim() -> None:
    response = client.post("/claims/triage", json={"claim_text": ""})

    assert response.status_code == 422


def test_triage_endpoint_rejects_a_missing_claim_text_field() -> None:
    response = client.post("/claims/triage", json={})

    assert response.status_code == 422


def test_triage_endpoint_serializes_tool_results(monkeypatch) -> None:
    def _fake_run_triage(claim_text: str, *, provider=None) -> TriageResult:
        return TriageResult(
            answer='{"eligible": true, "explanation": "You are eligible for EUR 250."}',
            decision=TriageDecision(eligible=True, explanation="You are eligible for EUR 250."),
            tool_results=(ToolResult(call_id="call-1", name="check_eligibility", content="{}", is_error=False),),
        )

    monkeypatch.setattr(routes, "run_triage", _fake_run_triage)

    response = client.post("/claims/triage", json={"claim_text": "My flight was cancelled."})

    assert response.status_code == 200
    assert response.json()["tool_results"] == [
        {"call_id": "call-1", "name": "check_eligibility", "content": "{}", "is_error": False}
    ]


def test_triage_endpoint_propagates_use_case_errors_as_a_server_error(monkeypatch) -> None:
    def _fake_run_triage(claim_text: str, *, provider=None) -> TriageResult:
        raise RuntimeError("triage did not converge within 8 tool-use turns")

    monkeypatch.setattr(routes, "run_triage", _fake_run_triage)

    with pytest.raises(RuntimeError):
        client.post("/claims/triage", json={"claim_text": "My flight was cancelled."})


def test_triage_stream_endpoint_emits_sse_frames_for_each_event(monkeypatch) -> None:
    call = ToolCall(id="call-1", name="check_eligibility", arguments={})

    def _fake_stream_triage(claim_text: str, *, provider=None) -> Iterator[StreamEvent]:
        assert claim_text == "My flight was cancelled."
        yield TextDelta(text="Checking eligibility...")
        yield ToolCallDelta(call=call)
        yield ToolResultEvent(result=ToolResult(call_id="call-1", name="check_eligibility", content="{}"))
        yield TurnDone(text="You are eligible for EUR 250.", tool_calls=(), stop_reason="end_turn", content=[])

    monkeypatch.setattr(routes, "stream_triage", _fake_stream_triage)

    response = client.post("/claims/triage/stream", json={"claim_text": "My flight was cancelled."})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [line for line in response.text.split("\n\n") if line]
    assert frames[0] == 'data: {"type": "text_delta", "text": "Checking eligibility..."}'
    assert '"type": "tool_call"' in frames[1]
    assert '"type": "tool_result"' in frames[2]
    assert '"type": "turn_done"' in frames[3]
    assert '"text": "You are eligible for EUR 250."' in frames[3]


def test_triage_stream_endpoint_rejects_an_empty_claim() -> None:
    response = client.post("/claims/triage/stream", json={"claim_text": ""})

    assert response.status_code == 422
