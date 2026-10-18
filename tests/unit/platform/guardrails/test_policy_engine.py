import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest
from pydantic import JsonValue

from ombuds.platform.guardrails.policy_engine import POLICY_UNAVAILABLE, OpaHttpPolicyEngine, PolicyDecision

_INPUT: dict[str, JsonValue] = {
    "action": "issue_payment",
    "payload": {"amount_eur": 600},
    "limits": {"max_payout_eur": 400},
}


def _respond(monkeypatch: pytest.MonkeyPatch, body: Any = None, error: Exception | None = None) -> list[Any]:
    sent: list[Any] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        sent.append((request.full_url, json.loads(request.data or b"{}"), timeout))  # type: ignore[arg-type]
        if error is not None:
            raise error
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return sent


def test_it_posts_the_input_to_the_payout_decision_document_and_parses_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _respond(
        monkeypatch,
        {"result": {"allow": False, "reasons": ["payout_above_limit"], "policy_version": "1"}},
    )

    decision = OpaHttpPolicyEngine("http://opa:8181/", timeout_seconds=1.5).evaluate(_INPUT)

    assert decision == PolicyDecision(allow=False, reasons=("payout_above_limit",), policy_version="1")
    assert sent == [("http://opa:8181/v1/data/ombuds/payout/decision", {"input": _INPUT}, 1.5)]


@pytest.mark.parametrize(
    "failure",
    [
        {"body": {}},  # OPA answers with no `result` when the document is undefined
        {"body": {"result": {"reasons": []}}},  # `allow` missing
        {"body": {"result": "yes"}},
        {"error": urllib.error.URLError("connection refused")},
        {"error": TimeoutError()},
    ],
)
def test_any_failure_to_get_a_decision_denies(monkeypatch: pytest.MonkeyPatch, failure: dict[str, Any]) -> None:
    _respond(monkeypatch, **failure)

    decision = OpaHttpPolicyEngine("http://opa:8181").evaluate(_INPUT)

    assert decision.allow is False
    assert decision.reasons == (POLICY_UNAVAILABLE,)
