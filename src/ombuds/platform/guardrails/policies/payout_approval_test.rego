package ombuds.payout_test

import rego.v1

import data.ombuds.payout

pay(amount) := {"action": "issue_payment", "payload": {"claim_id": "c-1", "amount_eur": amount}, "limits": {"max_payout_eur": 400}}

test_payout_below_limit_is_allowed if payout.allow with input as pay(250)

test_payout_at_limit_is_allowed if payout.allow with input as pay(400)

test_payout_one_above_limit_is_denied if {
	not payout.allow with input as pay(401)
	payout.decision.reasons == ["payout_above_limit"] with input as pay(401)
}

test_payout_with_non_numeric_amount_is_denied if {
	not payout.allow with input as pay("250")
	payout.decision.reasons == ["payout_amount_invalid"] with input as pay("250")
}

test_payout_with_missing_amount_is_denied if {
	not payout.allow with input as {"action": "issue_payment", "payload": {"claim_id": "c-1"}, "limits": {"max_payout_eur": 400}}
}

test_payout_without_a_limit_is_denied if {
	payout.decision.reasons == ["payout_limit_missing"] with input as {"action": "issue_payment", "payload": {"claim_id": "c-1", "amount_eur": 100}}
}

test_log_claim_is_not_subject_to_the_payout_limit if payout.allow with input as {"action": "log_claim", "payload": {"claim_id": "c-1", "compensation_eur": 600}, "limits": {"max_payout_eur": 400}}

test_decision_carries_the_policy_version if payout.decision.policy_version == "1" with input as pay(100)
