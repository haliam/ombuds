-- Append-only audit trail (ADR-0016): one row per tool call, policy verdict and approval transition. Rows are
-- never updated or deleted; the triggers make that a database guarantee, not a convention. `claim_id` and
-- `approval_request_id` are plain text with no foreign keys, so an event is recorded even for a claim that was
-- never logged or a request that was never created (a policy denial). `trace_id` is filled by W4 tracing.
CREATE TABLE audit_log (
    id                  BIGSERIAL PRIMARY KEY,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind                TEXT NOT NULL CHECK (kind IN (
        'tool_call', 'policy_decision',
        'approval_submitted', 'approval_approved', 'approval_denied', 'approval_executed'
    )),
    subject             TEXT NOT NULL,
    outcome             TEXT NOT NULL,
    claim_id            TEXT,
    approval_request_id TEXT,
    detail              JSONB NOT NULL DEFAULT '{}'::jsonb,
    trace_id            TEXT
);
CREATE INDEX audit_log_claim_idx ON audit_log (claim_id, id) WHERE claim_id IS NOT NULL;
CREATE INDEX audit_log_request_idx ON audit_log (approval_request_id, id) WHERE approval_request_id IS NOT NULL;

CREATE FUNCTION audit_log_reject_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_row_change BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_reject_change();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_reject_change();
