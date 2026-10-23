# ADR-0016: Append-only Postgres audit log, written at the governance seams

**Status:** accepted
**Date:** 2026-10-18

## Context
AGENTS.md calls ombuds "governed and observable", and the W4 task is "log every tool call + decision". Before this, the facts were scattered: tool calls lived only in the response (`tool_results`), approval rows were updated in place (so history was lost), and a policy verdict (ADR-0015) was either an exception or nothing. The question to answer afterwards is "what did the system do for claim X, and who allowed it?".

## Decision
- **One table, `audit_log`** (migration 0003), one row per event: `kind` (`tool_call`, `policy_decision`, `approval_submitted|approved|denied|executed`), `subject` (tool or action), `outcome`, `claim_id`, `approval_request_id`, a `detail` JSONB and a nullable `trace_id` (filled by the tracing task, no further migration).
- **Append-only in the database:** triggers reject `UPDATE`, `DELETE` and `TRUNCATE`. The guarantee does not depend on the application behaving.
- **Written at the seams that already exist**, as decorators, so no tool or node knows about auditing:
  - `AuditedDispatcher` around the tool registry (innermost, so it records PII-redacted, claim-pinned arguments; ADR-0013, ADR-0009),
  - `PolicyCheckedApprovalStore` records every verdict, allow or deny, with reason codes and `policy_version`,
  - `AuditedApprovalStore` around the Postgres store, *inside* `ExecutingApprovalStore`, so `approve` and `claim_for_execution` are separate events and the crash-recovery path is audited too.
  `build_runtime` wires all three, so the API and the MCP subprocess audit identically.
- **No raw data:** arguments and results are redacted (results also truncated); approval payloads and approver notes are not copied, only ids and the approver.
- **Refusals are events too (migration 0004, 2026-10-23):** `tool_refused` is written by the agent scope (`scope_for_agent`) for a call outside the agent's tool set, with the claim id, the call id and redacted arguments, because that call never reaches `AuditedDispatcher`. `injection_escalation` is written by the use case when a claim is escalated before the model, with counts per finding kind and never the matched text. Both go through an `audit` sink passed to `run_triage`/`stream_triage` (the API takes it from `app.state.audit`, set from `build_runtime`).
- **Errors are loud, not atomic:** `PostgresAuditLog.record` raises on a database error, so the caller sees the failure rather than a silent gap. It does not gate the action: the row is written after the effect (see Consequences).

## Consequences
- Easier: a claim's story is one ordered query (`PostgresAuditLog.for_claim`); denials that create no approval request are still visible.
- Harder: tests cannot truncate `audit_log`; integration tests use unique claim ids instead.
- Not atomic: the audit insert is its own transaction, after the state change. A crash between the two loses that one event. Making them one transaction would mean threading a connection through the store and is deferred.
- Not covered: there is no read endpoint, only the repository and SQL. A refusal is recorded only when an `audit` sink is passed; the API and the in-process runtime pass one, the MCP server does not scope calls and so has nothing to refuse.

## Alternatives considered
- **Structured logs only:** cheap, but not queryable per claim, not tamper-resistant, and PII hygiene depends on every call site.
- **Audit inside each tool / store method:** every new tool would have to remember it. Decorators cover MCP and in-process callers uniformly.
- **Event sourcing the approvals table:** stronger, but a rewrite of ADR-0009's compare-and-set design for this task's benefit.

Diagram: [Claim Artifact Map v1.0](../diagrams/artifact-map/README.md)
