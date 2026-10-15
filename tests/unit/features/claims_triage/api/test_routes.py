import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ombuds.api_app import create_app
from ombuds.features.claims_triage.api import routes
from ombuds.features.claims_triage.api.schemas import MAX_CLAIM_TEXT_CHARS
from ombuds.features.claims_triage.application.decision import TriageDecision
from ombuds.features.claims_triage.application.triage_use_case import (
    TriageCompleted,
    TriageResult,
    TriageStreamEvent,
)
from ombuds.platform.ai.providers.base import ProviderUnavailableError
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolResult
from ombuds.platform.ai.streaming import ToolCallDelta, ToolResultEvent
from ombuds.platform.guardrails.approval_gate import ApprovalGate

client = TestClient(create_app(ApprovalGate()))


def test_triage_endpoint_returns_the_use_case_result(monkeypatch) -> None:
    def _fake_run_triage(claim_text: str, *, approvals, provider=None) -> TriageResult:
        assert claim_text == "My flight was cancelled."
        return TriageResult(
            claim_id="CLM-1", answer="Please provide your flight details.", decision=None, tool_results=()
        )

    monkeypatch.setattr(routes, "run_triage", _fake_run_triage)

    response = client.post("/claims/triage", json={"claim_text": "My flight was cancelled."})

    assert response.status_code == 200
    assert response.json() == {
        "claim_id": "CLM-1",
        "answer": "Please provide your flight details.",
        "decision": None,
        "tool_results": [],
        "escalated": False,
        "escalation_reason": None,
    }


def test_triage_endpoint_surfaces_an_escalated_result(monkeypatch) -> None:
    def _fake_run_triage(claim_text: str, *, approvals, provider=None) -> TriageResult:
        return TriageResult(
            claim_id="CLM-1",
            answer="This claim could not be resolved automatically and needs human review.",
            decision=None,
            tool_results=(),
            escalated=True,
            escalation_reason="did not converge within 8 tool-use turns",
        )

    monkeypatch.setattr(routes, "run_triage", _fake_run_triage)

    response = client.post("/claims/triage", json={"claim_text": "My flight was cancelled."})

    assert response.status_code == 200
    body = response.json()
    assert body["escalated"] is True
    assert body["escalation_reason"] == "did not converge within 8 tool-use turns"


def test_triage_endpoint_rejects_an_empty_claim() -> None:
    response = client.post("/claims/triage", json={"claim_text": ""})

    assert response.status_code == 422


def test_triage_endpoint_rejects_a_claim_over_the_length_cap() -> None:
    response = client.post("/claims/triage", json={"claim_text": "x" * (MAX_CLAIM_TEXT_CHARS + 1)})

    assert response.status_code == 422


def test_triage_endpoint_rejects_a_missing_claim_text_field() -> None:
    response = client.post("/claims/triage", json={})

    assert response.status_code == 422


def test_triage_endpoint_serializes_tool_results(monkeypatch) -> None:
    def _fake_run_triage(claim_text: str, *, approvals, provider=None) -> TriageResult:
        return TriageResult(
            claim_id="CLM-1",
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
    def _fake_run_triage(claim_text: str, *, approvals, provider=None) -> TriageResult:
        raise RuntimeError("triage did not converge within 8 tool-use turns")

    monkeypatch.setattr(routes, "run_triage", _fake_run_triage)

    with pytest.raises(RuntimeError):
        client.post("/claims/triage", json={"claim_text": "My flight was cancelled."})


def test_triage_stream_endpoint_emits_progress_frames_then_one_final_frame(monkeypatch) -> None:
    call = ToolCall(id="call-1", name="check_eligibility", arguments={})
    result = TriageResult(
        claim_id="CLM-1", answer="Please provide your flight details.", decision=None, tool_results=()
    )

    def _fake_stream_triage(claim_text: str, *, approvals, provider=None) -> Iterator[TriageStreamEvent]:
        assert claim_text == "My flight was cancelled."
        yield ToolCallDelta(call=call)
        yield ToolResultEvent(result=ToolResult(call_id="call-1", name="check_eligibility", content="{}"))
        yield TriageCompleted(result=result)

    monkeypatch.setattr(routes, "stream_triage", _fake_stream_triage)

    response = client.post("/claims/triage/stream", json={"claim_text": "My flight was cancelled."})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [json.loads(line.removeprefix("data: ")) for line in response.text.split("\n\n") if line]
    assert [frame["type"] for frame in frames] == ["tool_call", "tool_result", "final"]
    assert frames[2] == {
        "type": "final",
        "claim_id": "CLM-1",
        "answer": "Please provide your flight details.",
        "decision": None,
        "tool_results": [],
        "escalated": False,
        "escalation_reason": None,
    }


def test_triage_stream_endpoint_ends_with_an_error_frame_when_the_provider_is_unavailable(monkeypatch) -> None:
    call = ToolCall(id="call-1", name="check_eligibility", arguments={})

    def _fake_stream_triage(claim_text: str, *, approvals, provider=None) -> Iterator[TriageStreamEvent]:
        yield ToolCallDelta(call=call)
        raise ProviderUnavailableError("overloaded")

    monkeypatch.setattr(routes, "stream_triage", _fake_stream_triage)

    response = client.post("/claims/triage/stream", json={"claim_text": "My flight was cancelled."})

    assert response.status_code == 200
    frames = [json.loads(line.removeprefix("data: ")) for line in response.text.split("\n\n") if line]
    assert [frame["type"] for frame in frames] == ["tool_call", "error"]


def test_triage_stream_endpoint_rejects_an_empty_claim() -> None:
    response = client.post("/claims/triage/stream", json={"claim_text": ""})

    assert response.status_code == 422
