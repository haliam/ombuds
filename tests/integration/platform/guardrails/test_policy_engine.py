"""The real payout policy, evaluated by a real OPA server (docker compose `opa` service, or `OPA_URL`)."""

import os
import urllib.error
import urllib.request

import pytest
from pydantic import JsonValue

from ombuds import config
from ombuds.platform.guardrails.policy_engine import OpaHttpPolicyEngine


@pytest.fixture(scope="module")
def engine() -> OpaHttpPolicyEngine:
    try:
        urllib.request.urlopen(f"{config.OPA_URL}/health", timeout=2)  # noqa: S310
    except urllib.error.URLError as exc:
        unreachable = f"OPA not reachable ({exc}); run `make opa-up`"
        if os.environ.get("CI"):
            pytest.fail(unreachable)  # a silent skip would let CI pass without testing anything
        pytest.skip(unreachable)
    return OpaHttpPolicyEngine(config.OPA_URL)


def _payment(amount_eur: JsonValue) -> dict[str, JsonValue]:
    return {
        "action": "issue_payment",
        "payload": {"claim_id": "c-1", "amount_eur": amount_eur},
        "limits": {"max_payout_eur": 400},
    }


def test_a_payout_at_the_limit_is_allowed(engine: OpaHttpPolicyEngine) -> None:
    decision = engine.evaluate(_payment(400))

    assert decision.allow is True
    assert decision.policy_version == "1"


def test_a_payout_above_the_limit_is_denied_with_a_reason(engine: OpaHttpPolicyEngine) -> None:
    decision = engine.evaluate(_payment(600))

    assert decision.allow is False
    assert decision.reasons == ("payout_above_limit",)


def test_a_policy_decision_is_returned_for_log_claim_regardless_of_amount(engine: OpaHttpPolicyEngine) -> None:
    decision = engine.evaluate(
        {"action": "log_claim", "payload": {"compensation_eur": 600}, "limits": {"max_payout_eur": 400}}
    )

    assert decision.allow is True
