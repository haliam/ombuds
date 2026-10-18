# Payout approval policy (ADR-0015).
#
# Evaluated when a guarded action is *submitted* for human approval. A deny means no approval request is
# created at all, so a human cannot approve an over-limit payout from the queue; it has to be handled outside
# the automated path. Anything not named here is allowed through to the normal human-approval flow.
#
# Input, all server-issued (never model-authored, ADR-0009):
#   input.action                    "issue_payment" | "log_claim"
#   input.payload.amount_eur        rules-derived payout amount (issue_payment only)
#   input.limits.max_payout_eur     ceiling from config (PAYOUT_LIMIT_EUR), passed in so it is not hardcoded here
package ombuds.payout

import rego.v1

policy_version := "1"

default allow := false

allow if count(reasons) == 0

# `object.get` with a null default: a field missing from the input must count as "not a number" (fail closed),
# but an undefined reference inside `not` would make the whole rule undefined and let the payment through.
amount := object.get(input, ["payload", "amount_eur"], null)

limit := object.get(input, ["limits", "max_payout_eur"], null)

reasons contains "payout_above_limit" if {
	input.action == "issue_payment"
	is_number(amount)
	is_number(limit)
	amount > limit
}

reasons contains "payout_amount_invalid" if {
	input.action == "issue_payment"
	not is_number(amount)
}

reasons contains "payout_limit_missing" if {
	input.action == "issue_payment"
	not is_number(limit)
}

# What the Python engine reads: one document with the verdict, the reason codes and the policy version.
decision := {
	"allow": allow,
	"reasons": sort(reasons),
	"policy_version": policy_version,
}
