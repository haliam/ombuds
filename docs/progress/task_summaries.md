# ombuds — Build Task Summaries

One entry per finished task from `tasks.md`. Recap for future-you, not documentation — that stays in docstrings/ADRs. Newest entries at the bottom.

Template — copy this block per finished task, filling in the fields (omit **Decisions/trade-offs** and **Follow-up** when there's nothing non-obvious to say):

```
### <task name from checklist>

**Week:** <W1/W2/W3/W4, matching the section in tasks.md>
**Goal:** <one sentence — the problem this task solves>
**Source:** <ADR # / Notion task, if any>

**Files & responsibilities:**
- `file.py` — what it's responsible for, one line (bare filename; add a directory prefix only to disambiguate two files sharing a name)

**Notable libraries:** <only libraries doing something non-obvious here — skip repeating pytest/mypy/ruff every time>

**Decisions/trade-offs:** <optional — a judgment call you made and why>
**Follow-up:** <optional — only if something's deliberately deferred>
```

---

### Implement EU261 rules engine (`verticals/airline/rules.py`) + unit tests

**Week:** W1
**Goal:** Give the agent a deterministic, legally-grounded eligibility/compensation calculator so the LLM never invents EU261 numbers itself.
**Source:** ADR-0004 (EU261 tool set); Regulation (EC) 261/2004, CJEU *Sturgeon* (C-402/07)

**Files & responsibilities:**
- `evidence_schema.py` — `FlightDisruption`/`Reroute` models: the facts a claim must establish (distance, scope, notice given, reroute offered) before rules can run. Facts only, no judgments.
- `rules.py` — `evaluate()`: scope check (Art. 3) → extraordinary-circumstances exemption (Art. 5(3)) → delay threshold (Art. 7, *Sturgeon*) → cancellation-notice exemption (Art. 5(1)(c)) → compensation tier by distance (Art. 7(1)) → reroute reduction (Art. 7(2)). First exemption found wins.
- `claim.py` — `EligibilityResult`: the vertical-agnostic output shape (`eligible`, `compensation_eur`, machine-readable `reasons`).
- `test_rules.py` — boundary tests for every threshold (distance tiers, 3h delay cutoff, 7/14-day notice windows), built from one baseline `disruption(**overrides)` factory per `docs/code-style.md`.

**Notable libraries:**
- Pydantic (`frozen=True` models) — evidence is immutable once constructed, so a rule function can't accidentally mutate its input.
- `enum.StrEnum` — `Reason` codes are a closed, serializable set an LLM can cite without re-deriving why.
- `datetime.timedelta` — every duration (notice, delay, reroute shift) is a `timedelta`, never a bare int of hours, so units can't be mixed up.

**Decisions/trade-offs:** Deliberately simplified subset of EU261 — voluntary denied boarding, missed connections across bookings, care/assistance rights, and UK261 are explicitly out of scope (documented in the module docstring) rather than half-implemented.

---

### Call OpenAI & Anthropic APIs directly, compare outputs

**Week:** W1
**Goal:** Eyeball raw provider SDKs (text, latency, cost) on the same prompt before building any shared abstraction over them.
**Source:** "Raw API Fundamentals" checklist

**Files & responsibilities:**
- `compare_providers.py` — throwaway script, not part of the runtime provider layer (`platform/ai/providers/` is still stubbed). Calls Anthropic, OpenAI, and DeepSeek with the same EU261 prompt and prints text + latency + estimated cost side by side.

**Notable libraries:**
- `anthropic` / `openai` SDKs — call each provider directly, no shared client; DeepSeek reuses the `openai` SDK since it exposes an OpenAI-compatible endpoint (same client, different `base_url`).
- `python-dotenv` (`load_dotenv`) — loads API keys from `.env` for a local script run, not the app's own config path.
- `dataclasses` (`@dataclass(frozen=True)`) — `ProviderResult` is a plain immutable record; no cross-layer boundary here, so no Pydantic needed (per `docs/code-style.md`: Pydantic is for models crossing a layer boundary).

**Decisions/trade-offs:** Cost is an estimate hardcoded from published pricing at write-time, flagged in a comment to re-verify before trusting it — not fetched live.

---

### Stub `approval_gate` as deny-all before any state-changing tool is registered

**Week:** W1
**Goal:** Guarantee a state-changing tool (`log_claim`, `issue_payment`) can never execute before a real approval mechanism exists — even temporarily.
**Source:** ADR-0004

**Files & responsibilities:**
- `approval_gate.py` — defines `GuardedAction` (which actions require approval) and `check_approval()`; currently denies every action unconditionally.
- `test_approval_gate.py` — pins that every `GuardedAction` is denied, parametrized so a new guarded action is covered automatically.

**Notable libraries:**
- Pydantic (`BaseModel`, `ConfigDict(frozen=True)`) — makes `ApprovalDecision` a validated, immutable result object instead of a raw dict.
- `enum.StrEnum` — closed, typo-proof set of guarded action names.

**Follow-up:** Stub only; replaced by the real human-approval gate in W2.

---

### Define tool schemas (`check_eligibility`, `log_claim`) + parse tool-use loop

**Week:** W1
**Goal:** Give both tools a provider-agnostic schema an LLM's tool-use request can validate against, and a dispatcher that turns a provider turn's tool calls into results without an if/elif per tool.
**Source:** ADR-0004 (EU261 tool set)

**Files & responsibilities:**
- `tool_calls.py` — `ToolDefinition` (name, description, `args_model`), `ToolCall`, `ToolResult`: the provider-agnostic shape a tool-use turn is parsed into/out of, independent of any specific SDK's response type.
- `tool_loop.py` — `ToolRegistry`: maps tool name → schema + handler; `dispatch()`/`dispatch_all()` validate arguments against the tool's `args_model` and run the handler, turning an unknown tool or a validation failure into an error `ToolResult` rather than an exception, so one bad call can't abort the rest of a turn.
- `check_eligibility.py` — read-only tool; reuses `FlightDisruption` as its own `args_model` and dispatches straight to `verticals/airline/rules.evaluate()`.
- `log_claim.py` — state-changing tool; `log_claim()` calls `approval_gate.check_approval()` before anything else and returns a denial result while the gate is the deny-all stub — persistence code isn't written yet since it's unreachable until W2.
- `test_tool_loop.py`, `test_check_eligibility.py`, `test_log_claim.py`.

**Notable libraries:** none new — same Pydantic/`StrEnum` patterns as the rules engine and approval gate.

**Decisions/trade-offs:** `check_eligibility`'s tool schema is `FlightDisruption` itself rather than a separate `CheckEligibilityArgs` wrapper — the tool takes exactly the rules engine's facts, so a second model would just duplicate the fields it's read-only over. `log_claim` raises `NotImplementedError` on the (currently unreachable) approved path rather than stubbing persistence, since there's no infrastructure layer yet to write to.
**Follow-up:** `issue_payment` still has no schema — deferred until it's wired up alongside `log_claim` in a later task; `tool_loop.ToolRegistry` isn't yet wired to a real provider response (that's the FastAPI `/triage` endpoint task next).

---

### Build FastAPI `/triage` endpoint (raw SDK, no framework)

**Week:** W1
**Goal:** Wire the existing `ToolRegistry` to a real provider turn and expose it as an HTTP endpoint — a raw `anthropic` SDK tool-use loop, not the LangGraph agent (that's a separate, later task).
**Source:** follow-up from the tool-schemas task

**Files & responsibilities:**
- `base.py` — `LLMProvider` Protocol (`run_turn`) and `ProviderTurn` (text, tool calls, stop reason, raw content), so `triage_use_case` isn't coupled to Anthropic's SDK types.
- `anthropic.py` — `AnthropicProvider.run_turn()`: converts `ToolDefinition`s to Anthropic's `input_schema` tool format, sends one `messages.create` call, and parses `tool_use`/`text` content blocks back into a `ProviderTurn`.
- `config.py` — `load_prompt()` reads the active versioned prompt file per AGENTS.md's prompt-versioning rule; `CLAIMS_TRIAGE_PROMPT_VERSION` in `.env.example` records which version (`v2`) is live.
- `v2.txt` — filled in the previously-empty stub with the system prompt: always call `check_eligibility` rather than reasoning about EU261 itself, cite its reason codes, and expect `log_claim` may be denied by the approval gate.
- `triage_use_case.py` — `run_triage()`: registers `check_eligibility`/`log_claim` on a `ToolRegistry`, loops `provider.run_turn()` → `registry.dispatch_all()` → feed `tool_result` blocks back, until the model stops requesting tools or `MAX_TOOL_TURNS` (8) is hit.
- `schemas.py`, `api/routes.py` — `TriageRequest`/`TriageResponse` and `POST /claims/triage`, thin per AGENTS.md.
- `api_app.py` — `create_app()` factory mounting the claims-triage router.
- `test_triage_use_case.py` — a fake `LLMProvider` (no real API calls) pins the no-tool-call, single-tool-call, unknown-tool, and max-turns-exceeded paths.
- `test_routes.py` — `TestClient` against the real app, `monkeypatch`ing `run_triage` so the route test doesn't depend on the use case's internals.

**Notable libraries:** FastAPI (`APIRouter`, `TestClient`) and its `httpx` dev dependency — both newly added to `pyproject.toml`.

**Decisions/trade-offs:** `LLMProvider.run_turn()` takes provider-native message dicts and returns a provider-specific `content` blob that's only ever replayed back into that same provider's next call — full provider-agnosticism across the message history was deferred since only Anthropic is wired up; `OpenAIProvider`/`fallback.py` stay stubs. `run_triage()` takes `provider` as an optional keyword so tests can inject a fake without a mocking framework.
**Follow-up:** streaming (SSE), structured-output retry/repair, and retries/backoff/fallback-model are their own W1 tasks next; a thorough unit-test pass over the tool-calling parser + endpoint (edge cases, malformed provider output) is the very next checklist item.

---

### Write unit tests for tool-calling parser + endpoint

**Week:** W1
**Goal:** Close edge-case gaps left after the FastAPI `/triage` task — the schemas, dispatch loop, and route had only happy-path coverage.
**Source:** follow-up from the FastAPI `/triage` endpoint task

**Files & responsibilities:**
- `test_tool_calls.py` (new) — `ToolDefinition.input_schema()` produces valid JSON Schema for its `args_model`; `ToolCall` is frozen (assignment raises); `ToolResult.is_error` defaults to `False`.
- `test_tool_loop.py` — added: `dispatch_all` doesn't abort the batch after one call fails (an unknown-tool error alongside a successful call in the same list); `definitions()` returns every registered `ToolDefinition`.
- `test_routes.py` — added: a request missing `claim_text` entirely (not just empty) returns 422; a non-empty `tool_results` tuple round-trips through JSON correctly; an unhandled exception from `run_triage` (e.g. the `MAX_TOOL_TURNS`-exceeded `RuntimeError`) propagates rather than being silently swallowed.

**Notable libraries:** none new — same pytest/`monkeypatch`/`TestClient` patterns as the existing route tests.

**Decisions/trade-offs:** the max-turns-exceeded `RuntimeError` is asserted to propagate as-is (via `pytest.raises`) rather than expecting a translated 500 response — the route currently has no exception handler, so this test documents current behavior rather than asserting a design that doesn't exist yet.
**Follow-up:** if `routes.py` later gets an explicit exception handler mapping use-case errors to a specific HTTP status, update this propagation test to assert on the response instead.

---

### Implement streaming (SSE) + buffered JSON parsing

**Week:** W1
**Goal:** Stream the triage answer and tool calls to the client as they happen instead of blocking until the whole tool-use loop finishes, and correctly assemble a tool call's arguments from the partial JSON fragments a streaming provider sends them in.
**Source:** follow-up from the FastAPI `/triage` endpoint task

**Files & responsibilities:**
- `streaming.py` — `StreamEvent` union (`TextDelta`, `ToolCallDelta`, `ToolResultEvent`, `TurnDone`) that any provider's stream is normalized to; `JSONBuffer` accumulates one tool call's `input_json_delta` fragments (keyed by call id) and parses them into a dict once that content block closes.
- `base.py` — `LLMProvider` Protocol gains `stream_turn()` alongside the existing `run_turn()`, returning `Iterator[StreamEvent]`.
- `anthropic.py` — `AnthropicProvider.stream_turn()` uses `client.messages.stream()`, yielding `TextDelta`/`ToolCallDelta` as raw SDK events arrive, then a final `TurnDone` built from `stream.get_final_message()` (not the accumulated deltas) so it matches `run_turn()`'s output exactly regardless of chunking.
- `triage_use_case.py` — `stream_triage()`: the same tool-use loop as `run_triage()`, but yields every `StreamEvent` from each turn plus a `ToolResultEvent` per dispatched tool call, instead of returning one final `TriageResult`.
- `routes.py` — `POST /claims/triage/stream`: `StreamingResponse` over `text/event-stream`, formatting each `StreamEvent` as one `data: <json>\n\n` frame. The original blocking `POST /claims/triage` is unchanged and kept alongside it.
- `test_streaming.py` (new) — `JSONBuffer` fragment assembly, independent tracking per call id, and the malformed/non-object-JSON error paths.
- `test_triage_use_case.py` — `_FakeProvider.stream_turn()` added so `stream_triage()` can be tested against the same fixtures as `run_triage()`, without a real API call.
- `test_routes.py` — SSE frame shape for the streaming endpoint, via `monkeypatch`ing `stream_triage` the same way `run_triage` is monkeypatched elsewhere.

**Notable libraries:** `anthropic`'s `messages.stream()` context manager (`MessageStreamManager`) and its raw event types (`content_block_start`/`_delta`/`_stop`) — distinct from the `messages.create()` path `run_turn()` uses.

**Decisions/trade-offs:** `stream_turn()`'s final `TurnDone` is rebuilt from `get_final_message()` rather than trusted to the deltas accumulated during the loop, so a provider-SDK quirk in delta chunking can't silently diverge the streamed result from what `run_turn()` would have returned for the same request. No unit test mocks the raw Anthropic SDK stream events directly (there's no existing precedent for that in this codebase, and the SDK's event types are a lot of surface to fake) — coverage instead treats `LLMProvider.stream_turn()` as the tested boundary, same as `run_turn()`/`ProviderTurn` today. Why the endpoint is SSE rather than a WebSocket is recorded in [ADR-0007](decisions/0007-sse-over-websockets-for-triage-streaming.md).
**Follow-up:** structured-output validation with retry/repair, and retries/backoff/fallback-model, are still open W1 tasks; a streaming path adds a new failure mode worth covering there (a stream that drops mid-tool-call).

---

### Add structured output validation with Pydantic + retry/repair

**Week:** W1
**Goal:** Stop trusting the model's final reply as free-form text once it has a decision — force it into a validated `TriageDecision` shape, and give it a chance to fix its own mistake instead of failing the whole triage the first time it emits malformed JSON.

**Files & responsibilities:**
- `structured_output.py` (new) — `parse_structured_output(text, schema)`: extracts the outermost `{...}` span from a reply (models wrap JSON in prose or a ```json fence even when told not to), `json.loads`s it, then `schema.model_validate`s it. Both failure modes raise one `StructuredOutputError` with a message written to be resent to the model verbatim.
- `decision.py` (new) — `TriageDecision`: the required final shape (`eligible`, `compensation_amount_eur`, `reason_codes`, `explanation`).
- `v3.txt` (new, now active) — same rules as v2, plus a "final answer format" section telling the model to reply with only that JSON object once it has a decision, and to resend a corrected object if told its JSON didn't validate. Plain-text replies (e.g. asking the passenger for a missing fact) are still allowed.
- `triage_use_case.py` — `run_triage()`: a final reply with no `{` in it is passed through unchanged as a plain-text answer (`decision=None`); one that contains `{` but fails to parse/validate triggers a repair turn (the validation error appended as the next user message) up to `MAX_REPAIR_ATTEMPTS` (2), after which `StructuredOutputError` propagates instead of being swallowed. `TriageResult` gained a `decision: TriageDecision | None` field.
- `schemas.py`, `api/routes.py` — `TriageResponse` and `POST /claims/triage` now surface `decision` alongside `answer`.
- `test_structured_output.py` (new) — clean JSON, JSON-in-prose extraction, no-JSON-object / malformed-JSON / schema-validation-failure error paths.
- `test_triage_use_case.py` — added: a plain-text final reply still returns `decision=None`; an invalid-then-valid JSON pair proves the repair loop recovers; exhausting `MAX_REPAIR_ATTEMPTS` raises `StructuredOutputError`.
- `test_routes.py` — updated fixtures to include `decision` in both the request and the serialized response.

**Notable libraries:** `pydantic.ValidationError` (surfaced as the repair-prompt text) and `typing.TypeVar` (`parse_structured_output` is generic over the schema so callers get back the concrete type they asked for, not a bare `BaseModel`) — see glossary.

**Decisions/trade-offs:** why prompted JSON + client-side repair was chosen over native structured-output enforcement is recorded in [ADR-0005](decisions/0005-prompted-json-with-repair-over-native-structured-output.md). `stream_triage()`/SSE was deliberately left unchanged: doing the same validation there would need a feature-specific event type inside `platform/ai/streaming.py`, which would break the `platform` → `features` import-direction rule in `AGENTS.md` (platform code can't know about a feature's `TriageDecision`). Bumped the active prompt straight to v3 rather than gating it behind `evals/` per `AGENTS.md`'s prompt-versioning rule, since `evals/run_evals.py` is still a no-op placeholder — there's nothing to gate against yet.
**Follow-up:** if `evals/` gets built out, re-validate v3 against it properly rather than treating this bump as final; `stream_triage()` still has no structured-output validation on its final turn.
**Correction (pre-W2 hardening, 2026-09-27):** this task's validation was shape-only — a reply that parsed as a valid `TriageDecision` was accepted even if it disagreed with `check_eligibility`'s actual result, or if `check_eligibility` was never called (W1 review finding F-01; the README's core claim, "the LLM never becomes the source of truth for the claim's outcome", was not actually true of the returned decision). Added `verify_decision()` in `application/decision.py`, checked against the latest successful `check_eligibility` result through the same repair loop this task built, and reworked `log_claim`'s arguments to take flight facts rather than an eligibility judgment so a model-authored `EligibilityResult` can never reach it either. Bumped the active prompt to v4 (same eval-gate caveat as v3's bump above — `evals/run_evals.py` is still a no-op placeholder). See ADR-0005's updated Consequences.

---

### Add retries/backoff, timeouts, fallback model, idempotency

**Week:** W1
**Goal:** Stop treating the Anthropic call as always-succeeds — add timeouts and backoff-retries for transient failures, fail over to a cheaper/secondary model if the primary keeps failing, and make retried requests idempotent so a retry (ours or the SDK's own) can't double-execute the same logical call.

**Files & responsibilities:**
- `anthropic.py` — `AnthropicProvider.__init__` now builds its `anthropic.Anthropic` client with `timeout`/`max_retries` (defaults 30s / 2 retries), delegating transient connection/429/5xx handling to the SDK's own exponential backoff instead of hand-rolling it. Added `_idempotency_key()`: a sha256 of `(model, system, messages, tool names)` sent as the `idempotency-key` header on both `run_turn()` and `stream_turn()`, so the same logical request (SDK retry, or a same-model retry from the layer below) dedupes server-side instead of re-running; a new turn (grown conversation) naturally gets a new key.
- `fallback.py` — `FallbackProvider`: wraps a `primary` and `fallback` `LLMProvider`, retrying `run_turn()` against `primary` with its own exponential backoff (`max_attempts`, default 3) before failing over to `fallback` entirely. `stream_turn()` does the same, but only fails over if the primary errors *before* any event has reached the caller — once output has started, a mid-stream failure is re-raised as-is rather than risking duplicate/replayed output. Also provides `build_default_provider()`, composing `ANTHROPIC_MODEL` as primary and `ANTHROPIC_FALLBACK_MODEL` as fallback from `config.py`.
- `config.py`, `.env.example` — new `ANTHROPIC_FALLBACK_MODEL` (default `claude-haiku-4-5`), `ANTHROPIC_TIMEOUT_SECONDS` (30), `ANTHROPIC_MAX_RETRIES` (2).
- `triage_use_case.py` — `run_triage()`/`stream_triage()` now default to `build_default_provider()` instead of a bare `AnthropicProvider()`, so triage gets retry/fallback behavior without callers changing anything (tests still inject `_FakeProvider` directly).
- `test_fallback.py` (new) — primary succeeds without retry; primary recovers within its retry budget; primary exhausts retries and `fallback` answers instead; a streaming failure before any output falls back; a streaming failure after output has started is re-raised, not swallowed. Uses an injectable `sleep` callable so backoff delays don't slow the test suite.
- `test_anthropic.py` (new) — `_idempotency_key()` is stable for an identical request, changes once the conversation grows, and changes with model.

**Notable libraries:** `anthropic.Anthropic(timeout=, max_retries=)` — the SDK's built-in httpx-based timeout/retry handling; no new third-party retry/backoff library was added since one layer's needs (client-level transient-error retry) were already covered by the SDK, and the other (cross-model fallback) needed custom fallover logic a generic decorator wouldn't express well.

**Decisions/trade-offs:** why the work is split into two resilience layers (SDK-level retries vs. `FallbackProvider`'s model fallover) instead of one retry library, and why `FallbackProvider` catches bare `Exception` (the one intentional exception to the no-bare-except rule in `docs/code-style.md`), is recorded in [ADR-0006](decisions/0006-two-layer-resilience-over-a-retry-library.md). Idempotency is scoped to the Anthropic provider's own header (derived from request content, not a random key), rather than a cross-provider idempotency scheme, since retrying against `fallback` is already a different model/request and doesn't need to dedupe against `primary`'s attempts.
**Follow-up:** `OpenAIProvider`/`fallback.py`'s provider-agnosticism is still untested against a live second provider (only two `AnthropicProvider` instances are composed today, since `OpenAIProvider` remains a stub); wiring OpenAI in as the fallback instead of a cheaper Anthropic model is a natural next step once that provider is implemented.
**Correction (pre-W2 hardening, 2026-09-27):** the `idempotency-key` header this task added was checked against the official Messages API reference and confirmed unsupported — Anthropic's Messages API does not document idempotency-key handling the way Stripe's API does, so `_idempotency_key()` and its header were doing nothing server-side. Removed from `anthropic.py` along with its tests. Idempotency belongs at the point where a duplicate call would actually cause harm — the state-changing tools (`log_claim`, `issue_payment`) landing in W2, keyed by `claim_id` — not at the LLM-call layer, which has no side effects to double-execute. See W1 review finding F-04.

---

### Rebuild tool-calling loop in LangGraph

**Week:** W2
**Goal:** Replace the W1 hand-rolled `for`-loop tool-use orchestration with an explicit LangGraph `StateGraph`, so the agentic loop is graph-native and later W2 nodes (classify/retrieve/decide/escalate_retry) have a graph to hang off of.
**Source:** `tasks.md` Week 2 checklist

**Files & responsibilities:**
- `state.py` — `AgentState`: the `TypedDict` threaded through every node (messages, accumulated `tool_results`, `pending_tool_calls`/`text` staging the latest model turn, `turns`/`repair_attempts` counters, `answer`/`decision`, `done`).
- `graph.py` — `build_triage_graph(provider, registry, system)`: compiles a 3-node graph — `call_model` (one provider turn) → routes to `dispatch_tools` (runs `ToolRegistry.dispatch_all`, loops back to `call_model`) or `finalize` (validates/verifies the final reply, either returning `answer`/`decision` or looping back to `call_model` with a repair message). Also hosts `tool_result_message()`, `_repair_message()`, `_parse_final_turn()` — moved here from `triage_use_case.py` since the loop now lives in this module.
- `triage_use_case.py` — `run_triage()` now builds and `.invoke()`s the compiled graph instead of a manual loop; same `TriageResult` contract, same `MAX_TOOL_TURNS`/`MAX_REPAIR_ATTEMPTS` bounds (now re-exported from `agent/graph.py`). `stream_triage()` is unchanged (streaming isn't threaded through the graph yet) but now imports `tool_result_message()` instead of duplicating it.
- `test_triage_use_case.py` — unchanged; passes against the graph-backed `run_triage()` with no test edits, confirming behavior parity (tool dispatch, repair-on-bad-JSON, repair-on-`verify_decision`-mismatch, unknown-tool error, non-convergence after `MAX_TOOL_TURNS`).
- `pyproject.toml` — added `langgraph>=0.2`.

**Notable libraries:** LangGraph (`StateGraph`, `CompiledStateGraph`, `END`) — see glossary.

**Decisions/trade-offs:** `stream_triage()` was deliberately left on the old manual loop rather than also rebuilt on the graph — streaming events (`TextDelta`/`ToolCallDelta`/`TurnDone`) aren't yet a first-class graph concept here, and folding them in would have doubled this task's scope for no behavior change; picked up as a later W2/W3 follow-up if streaming needs the same node structure. The tool-loop nodes (`call_model`/`dispatch_tools`/`finalize`) were written directly in `agent/graph.py` rather than split across `agent/nodes/*.py` (`classify.py`/`decide.py`/`retrieve.py`/`escalate_retry.py` per `AGENTS.md`'s layout) — those stubs are for the broader classify→retrieve→decide pipeline, which doesn't exist yet; wiring the tool loop into that node package is deferred to whichever task builds that pipeline, rather than guessing its shape now.
**Follow-up:** `agent/nodes/classify.py`, `retrieve.py`, `decide.py`, `escalate_retry.py` remain empty stubs — not wired into this graph. `stream_triage()` still bypasses the graph.

---

### Stand up MCP server (`search_kb`, `check_eligibility`, `log_claim`, `issue_payment`)

**Week:** W2
**Goal:** Expose the claims-triage tool catalogue over MCP, not just as an in-process `ToolRegistry`, so any MCP client (Claude Desktop, a future LangGraph MCP adapter) can list and call `search_kb`, `check_eligibility`, `log_claim` and `issue_payment` without knowing this feature exists.

**Files & responsibilities:**
- `search_kb.py` (new) — `SearchKbArgs`/`SearchKbResult`/`SEARCH_KB_TOOL`. Read-only, no approval gate. `search_kb()` always raises `ToolExecutionError`: `rag/retriever.py` is still a stub, so there's no real index to search yet — raising keeps that gap visible instead of returning empty or fabricated hits.
- `issue_payment.py` (new) — `IssuePaymentArgs`/`IssuePaymentResult`/`ISSUE_PAYMENT_TOOL`. State-changing; mirrors `log_claim`'s shape exactly: calls `check_approval(GuardedAction.ISSUE_PAYMENT)` first (denied unconditionally by the deny-all stub), then would raise `ToolExecutionError` for the disbursement path once approved — unreachable until the real approval gate lands.
- `__init__.py` — `build_tool_registry()` now registers all four tools instead of two.
- `tool_bindings.py` — `build_mcp_server(registry)`: builds an MCP `Server`, implementing `list_tools()`/`call_tool()` by reading straight from the given `ToolRegistry` — each tool's MCP `inputSchema` comes from `ToolDefinition.input_schema()`, so there's exactly one schema per tool, not a second one hand-written for MCP. `call_tool()` re-raises a `ToolRegistry.dispatch()` error result as a plain exception, which the MCP `Server` turns into an `isError=True` `CallToolResult` for the client.
- `server.py` — `python -m ombuds.platform.mcp.server`: the composition root (ADR-0003) that builds `claims_triage.tools.build_tool_registry()` and hands it to `build_mcp_server()`, then serves it over stdio via `mcp.server.stdio.stdio_server()`.
- `pyproject.toml` — added `mcp<2` (pinned below the newer, differently-shaped v2 SDK — `mcp==2.x` renamed `FastMCP`→`MCPServer` and moved the low-level `Server` to a callback-based constructor instead of `@server.list_tools()`/`@server.call_tool()` decorators) and `pytest-asyncio`, with `asyncio_mode = "auto"` so `async def test_...` needs no per-test marker.
- `test_search_kb.py`, `test_issue_payment.py` (new) — same shape as the existing `log_claim` tests: gate-denied result, `ToolExecutionError` once approved/for retrieval, argument validation, `ToolDefinition.args_model` identity.
- `test_tool_registry.py` — updated to assert all four tool names, not two.
- `test_tool_bindings.py` (new) — drives `build_mcp_server()` through a real in-memory MCP client/server session (`mcp.shared.memory.create_connected_server_and_client_session`) rather than calling `list_tools`/`call_tool` as bare functions, so the test exercises the actual MCP protocol layer (request/response (de)serialization included), not just the handler logic.

**Notable libraries:** `mcp` (the official Python MCP SDK) — see glossary for `Server`, the `list_tools`/`call_tool` decorators, `stdio_server`, and the in-memory test session helper. `anyio` — the async runtime `mcp`'s stdio transport is built on; `server.py`'s `main()` uses `anyio.run()` rather than `asyncio.run()` so it stays consistent with the library it's driving.

**Decisions/trade-offs:** verified the server for real, not just via the in-memory test — ran `python -m ombuds.platform.mcp.server` as an actual subprocess over stdio through `mcp.client.stdio.stdio_client()` and confirmed `list_tools`/`call_tool` round-trip correctly, since the in-memory session test alone wouldn't catch a stdio-transport-specific bug. Pinned `mcp<2` rather than adopting the newly-released v2 SDK: v2's low-level `Server` replaced the decorator API with constructor callbacks (`on_list_tools`/`on_call_tool`), a bigger, less-documented API surface change than this task needed to take on. `search_kb` and `issue_payment` are wired into the registry and reachable over MCP, but both are honest stubs (deny-all / retrieval-not-implemented) — same posture W1 left `log_claim` in; nothing here pretends the RAG pipeline or a payment provider exists yet.
**Follow-up:** "Connect LangGraph agent to tools over MCP" (next W2 task) should replace `application/triage_use_case.py`'s direct `ToolRegistry` use — now the graph built in "Rebuild tool-calling loop in LangGraph" above — with an MCP client. `search_kb` and `issue_payment` need real implementations once `rag/retriever.py` and the real approval gate land — this task only stood up the transport, not those backends.

---

### Connect LangGraph agent to tools over MCP

**Week:** W2
**Goal:** Give the LangGraph tool-calling loop (`agent/graph.py`) a real MCP-connected path to the claims-triage tools, so `search_kb`/`check_eligibility`/`log_claim`/`issue_payment` can be dispatched over the actual MCP transport stood up in the previous task, not just the in-process `ToolRegistry`.
**Source:** `tasks.md` Week 2 checklist

**Files & responsibilities:**
- `client.py` (new) — `McpToolClient`: a synchronous context manager wrapping an MCP `ClientSession` connected over stdio to `python -m ombuds.platform.mcp.server` (spawned as a subprocess). `definitions()` lists the server's tools and converts each to a `ToolDefinition` carrying the server's own JSON schema; `dispatch_all()` runs a batch of `ToolCall`s over the session, in order, converting each `CallToolResult` back to a `ToolResult`. Bridges LangGraph's synchronous nodes to the async-only `ClientSession` via an `anyio` blocking portal — `_connect()` opens the stdio transport and the session as one nested async context manager so enter/exit happen in the single task the portal keeps alive for it (`portal.wrap_async_context_manager`), avoiding a cancel-scope task-affinity error a naive `__aenter__`/`__aexit__` split hit during development.
- `tool_loop.py` — new `ToolDispatcher` `Protocol` (`definitions()`, `dispatch_all()`): the shape `agent/graph.py` actually needs from a tool source. `ToolRegistry` and `McpToolClient` both satisfy it structurally, so the graph doesn't know or care which one it's holding.
- `graph.py` — `build_triage_graph`'s `registry` parameter is now typed `ToolDispatcher` instead of `ToolRegistry`.
- `tool_calls.py` — `ToolDefinition` gained an optional `raw_schema` field; `input_schema()` returns it verbatim when set, falling back to `args_model.model_json_schema()` otherwise. An MCP-sourced definition has no local `args_model` to derive a schema from (validation happens server-side, inside the registry `platform/mcp/server.py` already wraps) — `raw_schema` lets it carry the server's schema through without a dummy model pretending to validate anything.
- `triage_use_case.py` — `run_triage()` gained a `use_mcp: bool = False` parameter; `True` runs the graph against an `McpToolClient` (spawning the server subprocess) instead of the default in-process `build_tool_registry()`. Both paths now share a `_invoke_graph()` helper instead of duplicating the `app.invoke()` call.
- `base.py`, `anthropic.py`, `fallback.py` — `run_turn`/`stream_turn`'s `tools` parameter widened from `list[ToolDefinition]` to `Sequence[ToolDefinition]`, so a `list[ToolDefinition]` from `ToolRegistry.definitions()` and one built by `McpToolClient.definitions()` are both accepted without either registry needing to match the other's exact list type.
- `test_client.py` (new) — real round-trip against the actual server subprocess (not the in-memory test session `test_tool_bindings.py` uses): lists the tool catalogue, dispatches `check_eligibility` and gets a real result back, and confirms an unknown tool name comes back as an `is_error` result rather than raising.
- `test_fallback.py`, `test_triage_use_case.py` — fake `LLMProvider` implementations' type hints updated to match the widened `Sequence[ToolDefinition]` signature; no behavior changes.

---

### Add short-term + long-term memory to agent state

**Week:** W2
**Goal:** Give the tool-calling loop somewhere to carry facts forward — within one run, and across separate runs for the same claimant — instead of only the raw `messages` transcript.
**Source:** `tasks.md` Week 2 checklist

**Files & responsibilities:**
- `short_term.py` — `ShortTermMemory`: a frozen, dict-of-facts Pydantic model scoped to one triage run. `remember()` returns a new instance (never mutates); `as_context()` renders the facts as a system-prompt block, or `None` if empty.
- `long_term.py` — `LongTermMemory` (same shape as `ShortTermMemory`, but meant to survive across runs) plus `LongTermMemoryStore`, a `Protocol` (`load(claimant_id)`/`save(claimant_id, memory)`) and `InMemoryLongTermMemoryStore`, a dict-backed default implementation that only lives for the process's lifetime — a placeholder until Postgres lands in W3.
- `state.py` — `AgentState` gained `short_term: ShortTermMemory` and `long_term: LongTermMemory`.
- `graph.py` — `call_model` now builds its system prompt via `_augmented_system()`, which appends `long_term.as_context()` then `short_term.as_context()` after the base prompt when either has facts. `dispatch_tools` records each successful tool result into `short_term` (keyed `f"{tool_name}_result"`) so later turns in the same run see it as plain context, not just buried in the tool-result message history.
- `triage_use_case.py` — `run_triage()` gained optional `claimant_id: str | None` and `long_term_store: LongTermMemoryStore | None` parameters. When both are given: the claimant's prior `LongTermMemory` is loaded before the run, the run's final decision is remembered under `"last_decision"`, and the result is saved back after. Omit either and the run only gets in-run `ShortTermMemory` — no cross-run recall, no behavior change from before this task. `_invoke_graph()` now returns `(TriageResult, LongTermMemory)` so the caller can persist the updated memory.
- `test_short_term.py`, `test_long_term.py` (new) — cover immutability of `remember()`, per-claimant isolation in `InMemoryLongTermMemoryStore`, and `as_context()` rendering/empty-case.
- `test_triage_use_case.py` — new cases: a decision is saved to the store under a claimant id; a later run for the same claimant sees the prior decision injected into its system prompt; no context is injected and nothing is touched when `claimant_id` is omitted.

**Decisions/trade-offs:** the API (`api/routes.py`) is deliberately left unwired to this — `TriageRequest` has no claimant identity field yet, and there's no real persistent store until W3's Postgres lands, so wiring the endpoint now would mean inventing an identity scheme just to plug it into an in-memory dict that resets on every server restart. `LongTermMemoryStore` is a protocol precisely so that wiring is a drop-in swap later, not a rewrite. Facts are stored as plain strings (not typed evidence) — this is prompt context for the model, not the source of truth for eligibility, which still comes from `check_eligibility` (`verify_decision`, ADR-0004/F-01) regardless of what memory says.

**Notable libraries:** `anyio.from_thread.start_blocking_portal` / `BlockingPortal.wrap_async_context_manager` — see glossary.

**Decisions/trade-offs:** `run_triage()` defaults to `use_mcp=False` rather than switching the whole app over to the MCP path — the in-process registry has no subprocess-startup cost and is what every existing test exercises; the MCP-connected path is opt-in and proven end-to-end (an integration test plus a manual run with a fake provider driving a real `check_eligibility` call over the subprocess), but nothing yet depends on it being the default. `ToolDefinition.raw_schema` was chosen over introducing a separate `ToolSpec` protocol type across the provider layer (which would have meant widening `LLMProvider.run_turn`/`stream_turn` and every implementer to a structurally-different type) — one optional field keeps `ToolDefinition` as the single currency both registries hand to a provider.
**Follow-up:** none of `run_triage`'s callers (the FastAPI `/triage` route) pass `use_mcp=True` yet — flipping that default, or exposing it as a request/config option, is a later decision once there's a reason to prefer the MCP path in production rather than just having it available and tested.

---

### Add escalation/retry loop on low confidence

**Week:** W2
**Goal:** Give the tool-calling graph a graceful "hand this to a human" outcome instead of raising a bare exception when it can't reach a confident decision — non-convergence, repeated repair/verification failure, or a stop_reason it can't recover from (F-09/F-10 from the pre-W2 review).
**Source:** `tasks.md` Week 2 checklist

**Files & responsibilities:**
- `escalate_retry.py` — no longer an empty stub. `UNRECOVERABLE_STOP_REASONS = {"max_tokens", "refusal"}` and `escalate(state)`, the terminal node: marks the run `done`/`escalated`, keeps `escalation_reason`, and falls back to a human-review message if there's no model text to return. First of the `agent/nodes/*.py` stubs to actually get wired into `agent/graph.py`.
- `graph.py` — `call_model` no longer raises `RuntimeError` past `MAX_TOOL_TURNS`; it returns an `escalation_reason` and lets `route_after_model` send the run to the new `escalate` node instead. It also checks each turn's `stop_reason` against `UNRECOVERABLE_STOP_REASONS`. `finalize`'s repair-exhaustion branch no longer re-raises `StructuredOutputError`; it sets `escalation_reason` and `route_after_finalize` routes to `escalate`.
- `state.py` — `AgentState` gained `stop_reason: str`, `escalated: bool`, `escalation_reason: str | None`.
- `triage_use_case.py` — `TriageResult` gained `escalated`/`escalation_reason` (defaulted `False`/`None` so existing construction sites don't need updating); `_invoke_graph` passes them through from the final graph state.
- `schemas.py`, `api/routes.py` — `TriageResponse` and the `/claims/triage` handler surface the same two fields to callers.
- `test_triage_use_case.py` — the three tests that used to assert a raised exception (`RuntimeError` on non-convergence, `StructuredOutputError` on repair exhaustion, both plain-mismatch and persistent-`verify_decision`-mismatch variants) now assert `result.escalated is True` with a matching `escalation_reason` instead; added a case for an unrecoverable `stop_reason="max_tokens"`.
- `test_routes.py` — updated the existing happy-path assertion for the two new response fields; added a case asserting an escalated `TriageResult` comes back as `escalated: true` with its reason.

**Decisions/trade-offs:** there's no model-reported confidence score anywhere in the schema (`TriageDecision` has none), so "low confidence" is operationalized as the three failure modes the pre-W2 review already flagged as escalation candidates (F-09 stop_reason, F-10 non-convergence/repair exhaustion) rather than inventing a confidence field the model would have to self-report and that nothing downstream could verify — `verify_decision` (ADR-0004/F-01) is still the only source of truth for eligibility, so a "low confidence" signal from the model itself wouldn't be trustworthy either. Escalation is expressed as normal graph state (`escalated`/`escalation_reason` fields on the final state, `TriageResult`, `TriageResponse`), not a raised exception — the F-10 write-up considered typed errors (`TriageDidNotConverge`, `DecisionInvalid`) with FastAPI exception handlers, but "the agent couldn't reach a confident decision" is a business outcome the caller needs to route to a human, not a 500; a typed-exception version would have needed the handler layer anyway to turn it back into a 200-with-a-flag response. `stream_triage()` (the raw, non-graph loop) is left untouched — it's already documented as a separate, deferred rebuild target, and folding escalation into it now would mean re-solving the same problem twice for a code path nothing currently depends on going through the graph.
**Follow-up:** `stream_triage()` still raises `RuntimeError` on non-convergence and has no escalation path — picked up whenever it's rebuilt on the graph. `agent/nodes/classify.py`, `retrieve.py`, `decide.py` remain empty stubs.

---

### Replace deny-all stub with human-approval gate before state-changing tool calls

**Week:** W2
**Goal:** Replace the W1 deny-all `approval_gate` stub (ADR-0004) with a real, if minimal, human-approval workflow — `log_claim`/`issue_payment` still can't disburse or persist anything without a human explicitly signing off, but there's now a way for that sign-off to actually happen.
**Source:** `tasks.md` Week 2 checklist; ADR-0008

**Files & responsibilities:**
- `approval_gate.py` — `check_approval(action, context)` now dedupes on `(action, context)` (e.g. `{"claim_id": ...}`) via a module-level `ApprovalGate`: the first call for a given action/context creates a `PENDING` `ApprovalRequest` and denies; a later call with the same action/context sees whatever a human resolved it to. `ApprovalGate` (`check`/`approve`/`deny`/`list_pending`/`get`) is the store's interface, in-memory and `threading.Lock`-guarded; `ApprovalStatus` (`PENDING`/`APPROVED`/`DENIED`) and `ApprovalNotFoundError` are new. Module-level `check_approval`/`list_pending_approvals`/`get_approval_request`/`approve_request`/`deny_request` wrap a single process-lifetime `_GATE` singleton.
- `api.py` (new) — `GET /approvals` (list pending), `POST /approvals/{id}/approve`, `POST /approvals/{id}/deny` (body: `approver`, optional `note`); 404s via `ApprovalNotFoundError`. Feature-agnostic, like `approval_gate.py` itself.
- `api_app.py` — mounts the new `approvals` router alongside the claims-triage feature's routes; this is one of the composition roots allowed to wire a platform-level router in directly (AGENTS.md).
- `log_claim.py`, `issue_payment.py` — `check_approval` calls now pass `{"claim_id": ...}` / `{"claim_id": ..., "amount_eur": ...}` as context, so the pending request a human sees is scoped to that specific claim rather than a bare action name.
- `test_approval_gate.py` — rewritten against a fresh `ApprovalGate()` per test (not the global singleton): first-check-creates-pending, same-context dedupes onto one request, different context creates a separate one, approve/deny resolve and are reflected on the next check, unknown request id raises.
- `test_api.py` (new) — drives the FastAPI routes through `TestClient`, monkeypatching `platform.guardrails.api`'s module-level functions to a scratch `ApprovalGate` per test so tests don't share state through the real singleton.
- `test_log_claim.py`, `test_issue_payment.py` — updated for the new denial message ("awaiting human approval" instead of "approval_gate stub"); the "approved → raises `ToolExecutionError`" monkeypatches now stub a two-arg `check_approval(action, context=None)`.

**Decisions/trade-offs:** In-memory store, not Postgres — the interview asked to choose between the two; in-memory was picked because `ApprovalGate`'s interface doesn't change if the backing store later does, so moving to Postgres (mirroring `audit_repository.py`) is a swap, not a rewrite, and there's no multi-worker deployment yet to make in-memory state actually wrong. First-sight behavior was the other explicit choice: `check_approval` auto-creates a `PENDING` request rather than requiring `log_claim`/`issue_payment` to create one explicitly first — keeps the tools themselves unchanged (same call site, same return shape) and puts request-creation in exactly one place. See ADR-0008 for the full write-up, including why this is necessarily poll-based (SSE, ADR-0007, is one-directional — a human's decision can't be pushed back into an in-flight triage run, only picked up on the *next* call).

**Notable libraries:** `threading.Lock` — see glossary.

**Follow-up:** The W2 task description also named idempotency on `claim_id` (W1 review F-04) as a requirement — `check_approval`'s dedup key already makes *approval requests* idempotent (a retried call for the same claim doesn't spawn a second pending request), but `log_claim`/`issue_payment` still don't persist anything (both still end in `raise ToolExecutionError(...not implemented...)` once approved), so true double-log/double-pay prevention at the persistence layer is still deferred to whenever W3's Postgres repository work lands — there's nothing to double-write yet. `approver` on `/approvals/*` is a free-text field with no authentication; fine for this demo, flagged in ADR-0008 as a gap a real deployment would need to close.

---

### Pre-W3 hardening

**Week:** W2 → W3 boundary
**Goal:** Fix the W2 governance-path gaps found in the pre-W3 review before W3 builds persistence, RAG and guardrails on top of them.
**Source:** [`w2_review_pre_w3_plan.md`](w2_review_pre_w3_plan.md) (T-1 to T-6, O-7); ADR-0009 (supersedes ADR-0008); ADR-0007 amendment

**Files & responsibilities:**
- `escalate_retry.py` — escalated runs return a fixed `ESCALATION_ANSWER`, never the model's last text, which on every escalation path was a rejected verdict, a stale preamble or a truncated reply (T-1, F-01).
- `short_term.py`, `long_term.py`, `graph.py`, `triage_use_case.py` — short-term memory holds only rules-derived eligibility fields and is never injected into a prompt; long-term memory consolidates those fields on a verified decision (no more model `explanation`) and is shown as a context block in the first user turn. The system prompt is now constant across a run (T-5, F-06).
- `0009-approval-request-is-the-pending-action.md` — the approval request *is* the pending action: tools only submit, an approved request executes exactly once via an executor, `claim_id` is server-issued, the agent isn't offered `issue_payment`, and `log_claim` is meant to auto-run under the W4 policy (T-2, F-05). README step 6 and AGENTS.md updated to match.
- `tools/__init__.py` — `scope_for_agent(dispatcher, claim_id)` wraps any `ToolDispatcher` (in-process or MCP): it offers only `search_kb`/`check_eligibility`/`log_claim`, refuses other calls without dispatching them, and overwrites `claim_id` with the run's (T-3/T-4, F-03).
- `approval_gate.py`, `guardrails/api.py` — `submit(action, payload)` dedupes on the canonical payload; `approve`/`deny` only from `PENDING` (409 otherwise); `claim_for_execution` is the single-use `APPROVED → EXECUTED` transition; `ApprovalRequest` is frozen; new `GET /approvals/{id}` (T-4, F-02).
- `log_claim.py`, `issue_payment.py` — both only submit. The payload is `claim_id` plus the rules-derived outcome plus the structured facts; `issue_payment` takes facts, not an amount, and derives the amount from `evaluate()` (T-4, F-04).
- `graph.py`, `triage_use_case.py`, `routes.py` — `/claims/triage/stream` runs the same graph (`build_triage_graph(stream=True)`); SSE frames are `tool_call`, `tool_result`, then one `final` frame with the `/triage` response fields, or `error` on `ProviderUnavailableError`. Unverified model text is never streamed; the W1 manual loop is deleted (T-6, F-07).
- `client.py`, `schemas.py`, `fallback.py`, `pyproject.toml` — the MCP client no longer leaks its portal thread on a failed connect; `claim_text` is capped at 10,000 chars; the `FallbackProvider` docstring is corrected; `openai` moved to a `scripts` dependency group (O-7).

**Notable libraries:** `langgraph.config.get_stream_writer`, `pydantic.JsonValue`, `contextlib.ExitStack` — see glossary.

**Decisions/trade-offs:** `claim_id` stays in the tools' argument schemas (MCP clients need it) and is *overwritten* for the agent rather than rejected, so no prompt change was needed and a model that guesses an id can't loop on errors. The stream dropped `text_delta`/`turn_done` frames rather than streaming the final reply's tokens, because until `finalize` verifies it, that reply is an unverified verdict. The prompt stayed on v4: the tool results are self-describing ("submitted for human approval"), and v5 waits for the W3 eval set. A separate style commit fixed 11 pre-existing lint findings that blocked `make lint` on HEAD.
**Follow-up:** executors and a Postgres-backed approval store (W3, per ADR-0009); DI at the composition root (O-1), the RAG entry point decision (O-2) and prompt v5 (O-3) stay in their W3 tasks. Commit `1c0ea0b` still has a placeholder message; rewording it needs a force-push to `origin/w2_final_review`.

---

Library/framework/stdlib-concept entries live in [`glossary.md`](glossary.md) — append there, not here, whenever a summary's **Notable libraries** introduces something not already listed.
