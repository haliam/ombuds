import pytest
from fastapi.testclient import TestClient

from ombuds.api_app import app
from ombuds.features.claims_triage.api import routes
from ombuds.features.claims_triage.application.triage_use_case import TriageResult
from ombuds.platform.ai.schemas.tool_calls import ToolResult

client = TestClient(app)


def test_triage_endpoint_returns_the_use_case_result(monkeypatch) -> None:
    def _fake_run_triage(claim_text: str, *, provider=None) -> TriageResult:
        assert claim_text == "My flight was cancelled."
        return TriageResult(answer="You are eligible for EUR 250.", tool_results=())

    monkeypatch.setattr(routes, "run_triage", _fake_run_triage)

    response = client.post("/claims/triage", json={"claim_text": "My flight was cancelled."})

    assert response.status_code == 200
    assert response.json() == {"answer": "You are eligible for EUR 250.", "tool_results": []}


def test_triage_endpoint_rejects_an_empty_claim() -> None:
    response = client.post("/claims/triage", json={"claim_text": ""})

    assert response.status_code == 422


def test_triage_endpoint_rejects_a_missing_claim_text_field() -> None:
    response = client.post("/claims/triage", json={})

    assert response.status_code == 422


def test_triage_endpoint_serializes_tool_results(monkeypatch) -> None:
    def _fake_run_triage(claim_text: str, *, provider=None) -> TriageResult:
        return TriageResult(
            answer="You are eligible for EUR 250.",
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
