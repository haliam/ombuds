# Plan: Week 4 implementation order

**Status: proposed (2026-10-18).** Task 1 (Rego policy) is done (ADR-0015); Task 2 (audit trail) is next.

## Context
Three open W4 tasks (docs/progress/tasks.md): OpenTelemetry tracing, one OPA/Rego payout policy, audit trail. All three are scaffolds today: `platform/guardrails/policy_engine.py` + `policies/payout_approval.rego`, `platform/infrastructure/audit_repository.py`, `platform/observability/tracing.py`. The pre-W4 refactor (P-1..P-4) already gave us the foundation: Postgres-backed approval store, executors, composition-root wiring. Per AGENTS.md: one task per chat, one commit per task.

## Order: Rego policy -> Audit trail -> OpenTelemetry

### 1. OPA/Rego policy (block auto-payout above EUR X)
Why first: it is the only task that changes behaviour, it is the non-negotiable guardrail, and it defines the decision record (allow/deny, reason, policy version) the other two must capture.
- Fill `payout_approval.rego`; implement `policy_engine.py` behind a small protocol (injected from the composition roots `api_app.py` and the MCP server, no module global).
- Check it inside the approval-gate submit path for `issue_payment` (input: server-issued amount, claim_id, action; never model-authored values, ADR-0009).
- Threshold from config, not hardcoded; unit tests for allow/deny/boundary; ADR for the engine choice (OPA sidecar vs. embedded evaluation).

### 2. Audit trail
Why second: it persists every tool call plus decision, including the policy verdict from step 1 and the approval transitions that already exist. Durable Postgres rows are the source of truth.
- Migration `0003` for an append-only audit table; implement `audit_repository.py`.
- Record at the seams already in place: guarded dispatcher (tool calls), approval store transitions, policy decisions.
- PII stays redacted (ADR-0013); no raw evidence payloads. Add a nullable `trace_id` column now so step 3 can fill it with no further migration.
- Integration test against real Postgres; unit tests per module.

### 3. OpenTelemetry tracing
Why last: it is cross-cutting and read-only. It wraps what steps 1 and 2 built, so it is written once and carries their data.
- Implement `tracing.py`; span per LLM call (provider layer), per tool call (dispatcher) and per policy check. Attributes include the policy decision and audit id.
- Write the active `trace_id` into audit rows.
- Exporter via config (OTLP/console); add collector to docker-compose only if cheap. Redact PII in span attributes.

## Verification
- `make test` (ruff, mypy strict, unit) after each task; `make test-integration` for audit and policy against Postgres.
- Manual: `make up`, triage a claim over the payout threshold, confirm the policy blocks it, an audit row exists, and a trace shows the spans.

## Alternative
Tracing first would make steps 1 and 2 easier to debug, but it would be revisited to add policy and audit attributes. Pick it only if you want visibility while building.
