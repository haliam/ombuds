-- Simulated payout records (ADR-0009 addendum): there is no real payment rail, so "issuing" a payment means
-- recording it here. One payment per claim; the executor's INSERT ... ON CONFLICT DO NOTHING makes a retried
-- execution a no-op, and the foreign key means a payment can only exist for a logged claim.
CREATE TABLE payments (
    claim_id            TEXT PRIMARY KEY REFERENCES claims (claim_id),
    amount_eur          INTEGER NOT NULL CHECK (amount_eur > 0),
    approval_request_id TEXT NOT NULL REFERENCES approval_requests (id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
