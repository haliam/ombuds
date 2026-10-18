"""Policy engine: asks OPA whether a guarded action may proceed (ADR-0015).

`PolicyEngine` is the small protocol the guardrails depend on; `OpaHttpPolicyEngine` is the runtime
implementation, talking to an OPA server over its REST API. The rules themselves live in
`policies/*.rego`, not here. The engine fails closed: if OPA is unreachable or answers with anything that
isn't a well-formed decision, the action is denied, never allowed.
"""

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

logger = logging.getLogger(__name__)

PAYOUT_DECISION_PATH = "v1/data/ombuds/payout/decision"
"""OPA document produced by `policies/payout_approval.rego`: `{allow, reasons, policy_version}`."""

POLICY_UNAVAILABLE = "policy_unavailable"
"""Reason code for a denial caused by the engine failing, not by a rule."""


class PolicyDecision(BaseModel):
    """The verdict on one input: allow or deny, with machine-readable reason codes and the policy version."""

    model_config = ConfigDict(frozen=True)

    allow: bool
    reasons: tuple[str, ...] = ()
    policy_version: str = "unknown"


class PolicyEngine(Protocol):
    """Evaluates one policy input; `OpaHttpPolicyEngine` and test fakes fit."""

    def evaluate(self, policy_input: Mapping[str, JsonValue]) -> PolicyDecision: ...


class OpaHttpPolicyEngine:
    """Queries an OPA server (`opa run --server`) for the payout decision document."""

    def __init__(self, base_url: str, timeout_seconds: float = 2.0, path: str = PAYOUT_DECISION_PATH) -> None:
        self._url = f"{base_url.rstrip('/')}/{path}"
        self._timeout_seconds = timeout_seconds

    def evaluate(self, policy_input: Mapping[str, JsonValue]) -> PolicyDecision:
        """Return OPA's decision for `policy_input`, or a deny with `policy_unavailable` if OPA can't answer."""
        request = urllib.request.Request(  # noqa: S310 - URL comes from config, scheme is http(s)
            self._url,
            data=json.dumps({"input": policy_input}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                body = json.load(response)
            return PolicyDecision.model_validate(body["result"])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, ValidationError):
            logger.warning("policy engine unavailable or returned no decision; denying", exc_info=True)
            return PolicyDecision(allow=False, reasons=(POLICY_UNAVAILABLE,))
