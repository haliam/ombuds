# ADR-0017: OpenTelemetry spans at the existing seams, with no content in attributes

**Status:** accepted
**Date:** 2026-10-18

## Context
W4 asks for a span per LLM call and per tool call. The seams already exist as decorators (ADR-0013, ADR-0015, ADR-0016), and the audit table has a nullable `trace_id` waiting for this task.

## Decision
- **Global OTel API, no-op by default.** Code calls `start_span`; `configure_tracing(config.OTEL_TRACES_EXPORTER)` in the two composition roots (`api_app.py`, the MCP server) installs a provider. `none` (default), `console` (stderr, since MCP owns stdout) or `otlp` (standard `OTEL_EXPORTER_OTLP_*` variables).
- **Spans as decorators:** `TracedProvider` around each concrete adapter (`llm.turn`, so a failover shows as two sibling spans), `TracedDispatcher` outside `AuditedDispatcher` (`tool.<name>`), a `policy.check` span in `PolicyCheckedApprovalStore`, and a `triage.run` root span in the use case (sync and streaming) so one claim is one trace.
- **No content in spans:** only ids, model, stop reason, counts, tool outcome and the policy verdict. Not prompts, claim text, tool arguments or results; an exception sets the status to its type name, never its message. The trace backend therefore needs no PII handling (ADR-0013).
- **Audit link:** `PostgresAuditLog.record` stamps `trace_id` from the active span, so an audit row maps to its trace.
- **Streaming:** `trace_stream` makes the span current only while the source produces an event, never across a `yield`, because FastAPI resumes sync generators on different threads and a context attached on one cannot be detached on another.

## Consequences
- Easier: swapping the backend is an env var; tests assert on spans with an in-memory exporter.
- Not covered: the MCP stdio subprocess (`use_mcp=True`) is a separate process and starts its own traces, since no context is propagated over stdio; there are no HTTP request spans (that would add `opentelemetry-instrumentation-fastapi`); no token-usage attributes yet, because `ProviderTurn` does not carry usage; no collector in docker-compose.

## Alternatives considered
- **Instrument inside tools and providers:** every new one would need to remember it.
- **Auto-instrumentation packages for Anthropic/OpenAI:** they capture prompts and completions by default, which conflicts with the no-PII rule.
