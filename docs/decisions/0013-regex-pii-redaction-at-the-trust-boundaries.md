# ADR-0013: One-way regex PII redaction at every trust boundary

**Status:** accepted
**Date:** 2026-10-08

## Context
The only free-text PII source is the passenger's `claim_text`. It went unmodified into the first user message, so it reached the Anthropic/OpenAI APIs, and the model's own tool arguments (notably `search_kb.query`, which is sent to the OpenAI embeddings API) and final answer could echo it. Structured data is already clean: `FlightDisruption` holds only flight facts, and ADR-0009 keeps `claim_text` out of approval payloads. Free text could also leak through log lines (`logger.exception`, provider error strings), the free-text approver `note`, the SSE `tool_call` frames, and external MCP clients calling `search_kb` directly. `pii_filter.py`, `logging.py` and the audit repository were one-line stubs.

## Decision
`platform/guardrails/pii_filter.py` exposes `redact(text)` (and `redact_value` for JSON-like arguments). It replaces matches with typed placeholders (`[EMAIL]`, `[IBAN]`, `[CARD]`, `[PHONE]`, `[PASSPORT]`, `[BOOKING_REF]`) and returns per-kind counts, never the values. It is applied at these points:

- **Input:** `run_triage` / `stream_triage` redact `claim_text` before the model sees it. The raw text is never persisted or logged.
- **Tool arguments:** `GuardedDispatcher` wraps any `ToolDispatcher` (in-process registry or MCP client), around `scope_for_agent`.
- **External MCP clients:** `platform/mcp/server.py`'s `build_server()` wraps the registry in `GuardedDispatcher`; `build_mcp_server` now takes any `ToolDispatcher`.
- **Output:** `_to_result` redacts `answer`, `decision.explanation` and `escalation_reason`; streamed `tool_call` frames carry redacted arguments.
- **Approvals:** `ApprovalGate.approve`/`deny` store the approver's `note` redacted.
- **Logs:** `PiiRedactingFilter` on every root and uvicorn handler (`configure_logging()`, called from both composition roots).
- **Audit log (governance stage):** nothing built here. The audit trail should store redacted text and `RedactionResult.findings` counts.

Detection is regex plus a checksum where one exists (Luhn for cards, mod-97 for IBANs). Phones need an international prefix or a separated national format. Passport and booking references are only redacted after a keyword, because a bare 6-character code collides with flight numbers such as `LH1234` and mangling flight facts would break eligibility. There is no config switch to turn the filter off.

## Consequences
- Easier: one small module with no new dependency or model download; deterministic and unit-testable, with a false-positive corpus (flight facts and the whole KB seed must pass through unchanged).
- Easier: every entry point, including MCP, shares the same filter, so a new tool or endpoint is covered by wrapping its dispatcher.
- Harder: **names and postal addresses are not detected**, and a booking reference or passport number without a keyword is not either. Regexes can't find names reliably, so a claim containing only a name reaches the model.
- A 13-digit airline ticket number that passes Luhn is redacted as `[CARD]`; a failed-checksum IBAN's digit runs can be caught as a phone or card. Over-redacting is the safe direction.
- Redaction is irreversible, so answers show placeholders (`[EMAIL]`) instead of the passenger's original details.
- Prompt v4 is untouched; the model sees placeholders. Mention them in v5 only if the evals show it matters.
- `ToolResult.content` is not filtered: it comes from our own typed tools or KB snippets. Revisit if a tool ever returns user text.
- FastAPI's 422 validation response echoes the offending `input` (e.g. an over-length `claim_text`) back to the caller. It is not logged, so it is left as is.

## Alternatives considered
- **Presidio + spaCy NER:** the production standard and the only way to catch names, but a heavy dependency and a model download for a four-week project. It can sit behind the same `redact()` signature later; revisit when name leakage matters.
- **Reversible tokenisation (a vault mapping placeholders back):** would let answers restore real details, but it keeps raw PII in a store that then needs its own protection.
- **Pydantic validators on the request model:** they validate known fields but can't find an email inside a sentence. Pydantic is used only for the result types.
- **Reject claims that contain PII:** passengers routinely include contact details, so rejecting would block ordinary claims.

Diagram: [Guardrails and Tool Scoping Pipeline v1.0](../diagrams/guardrails-pipeline/README.md)
