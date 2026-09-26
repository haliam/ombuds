from fastapi.testclient import TestClient

from ombuds.api_app import app
from ombuds.features.claims_triage.api import routes
from ombuds.features.claims_triage.application.triage_use_case import TriageResult

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
