"""Policy fakes for integration tests that are about something other than policy (see test_policy_checked_store)."""

from collections.abc import Mapping

from pydantic import JsonValue

from ombuds.platform.guardrails.policy_engine import PolicyDecision

PAYOUT_LIMIT_EUR = 400


class AllowAllPolicy:
    def evaluate(self, policy_input: Mapping[str, JsonValue]) -> PolicyDecision:
        return PolicyDecision(allow=True)
