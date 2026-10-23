-- Two more audit kinds (ADR-0016): a tool call the agent scope refused, and a claim escalated before the model
-- because it looked like a prompt injection. The `CHECK` is replaced, not the table: existing rows all satisfy
-- the wider list, and the append-only triggers (UPDATE/DELETE/TRUNCATE) are untouched.
ALTER TABLE audit_log DROP CONSTRAINT audit_log_kind_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_kind_check CHECK (kind IN (
    'tool_call', 'policy_decision',
    'approval_submitted', 'approval_approved', 'approval_denied', 'approval_executed',
    'tool_refused', 'injection_escalation'
));
