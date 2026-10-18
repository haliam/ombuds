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
- **Fail closed:** `PostgresAuditLog.record` raises on a database error, so an action does not proceed unaudited.

## Consequences
- Easier: a claim's story is one ordered query (`PostgresAuditLog.for_claim`); denials that create no approval request are still visible.
- Harder: tests cannot truncate `audit_log`; integration tests use unique claim ids instead.
- Not atomic: the audit insert is its own transaction, after the state change. A crash between the two loses that one event. Making them one transaction would mean threading a connection through the store and is deferred.
- Not covered: the pre-model injection escalation (ADR-0014) is a decision but happens before any tool or store, and is not yet recorded; there is no read endpoint, only the repository and SQL.

## Alternatives considered
- **Structured logs only:** cheap, but not queryable per claim, not tamper-resistant, and PII hygiene depends on every call site.
- **Audit inside each tool / store method:** every new tool would have to remember it. Decorators cover MCP and in-process callers uniformly.
- **Event sourcing the approvals table:** stronger, but a rewrite of ADR-0009's compare-and-set design for this task's benefit.
