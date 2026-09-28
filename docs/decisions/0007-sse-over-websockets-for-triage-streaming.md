# ADR-0007: Server-Sent Events over WebSockets for `/claims/triage/stream`

**Status:** accepted
**Date:** 2026-09-26

## Context
The triage loop already streams incrementally from the provider (text deltas, completed tool calls, per-turn results — `platform/ai/streaming.py`). Exposing that over HTTP needed a push mechanism a browser or simple HTTP client could consume without extra machinery. The traffic on this endpoint is one-directional: the client sends one claim, the server pushes events until the loop ends — the client never sends anything back mid-stream (no cancel-and-redirect, no follow-up message while the loop is running).

## Decision
Stream `/claims/triage/stream` as Server-Sent Events (`StreamingResponse` over `text/event-stream`, one `data: <json>\n\n` frame per `StreamEvent`), not a WebSocket.

## Consequences
- The endpoint stays a normal HTTP POST — a request body, one response, no separate upgrade handshake or connection-lifecycle protocol to manage on top of what FastAPI/Starlette already do for every other route in `api/routes.py`.
- Any HTTP client can consume it (`curl`, `EventSource` in a browser, the same `httpx`-based `TestClient` already used in `tests/unit/features/claims_triage/api/test_routes.py`) without a WebSocket-capable client or a second protocol to test against.
- Framing is one JSON object per SSE `data:` line, matching the same `StreamEvent` union the non-streaming path already returns as `tool_results` — one wire shape for the event data, two transports.
- Forecloses the client sending anything back once the stream starts (a mid-stream cancel, a follow-up answer to a clarifying question while the loop is running) without a second request. Not needed today: the loop's only mid-turn input is the tool results it dispatches itself, not anything the caller supplies.
- Revisit if the triage flow needs true bidirectional interaction mid-stream — e.g. a human-in-the-loop approval decision (W2/W3) delivered *while* a turn is still streaming, rather than as a separate request after the stream ends. SSE can't carry that; a WebSocket (or a second short-lived endpoint the client calls mid-stream) would be needed then.

## Amendment (2026-09-28, pre-W3 T-6)
The transport decision stands; what the frames carry changed. `/claims/triage/stream` now runs the same LangGraph graph as `/claims/triage` (W2 review F-07), and streams only `tool_call` and `tool_result` progress frames, then exactly one `final` frame with the same fields as the `/triage` response, or an `error` frame if the LLM provider is unavailable. Raw model text (`text_delta`/`turn_done`) is no longer streamed: a final reply is an unverified verdict until the graph's `finalize` step has checked it against `check_eligibility`, so streaming its tokens would leak exactly what verification exists to stop. Token-level streaming of *verified* passenger-facing text is a possible later addition, not a regression to restore.

## Alternatives considered
- **WebSockets.** Gives a bidirectional channel this endpoint doesn't use yet, at the cost of a connection-lifecycle protocol (open/ping-pong/close) and a client that must speak it, for no round-trip this flow currently needs.
- **Long polling.** Would mean the client re-requesting per chunk, reconstructing turn boundaries across requests that the current single-request tool-use loop doesn't need to expose.
