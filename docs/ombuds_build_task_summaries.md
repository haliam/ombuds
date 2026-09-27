# ombuds — Build Task Summaries

One entry per finished task from `ombuds_build_tasks.md`. Recap for future-you, not documentation — that stays in docstrings/ADRs. Newest entries at the bottom.

Template — copy this block per finished task, filling in the fields (omit **Decisions/trade-offs** and **Follow-up** when there's nothing non-obvious to say):

```
### <task name from checklist>

**Week:** <W1/W2/W3/W4, matching the section in ombuds_build_tasks.md>
**Goal:** <one sentence — the problem this task solves>
**Source:** <ADR # / Notion task, if any>

**Files & responsibilities:**
- `path/to/file.py` — what it's responsible for, one line

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
- `src/ombuds/features/claims_triage/verticals/airline/evidence_schema.py` — `FlightDisruption`/`Reroute` models: the facts a claim must establish (distance, scope, notice given, reroute offered) before rules can run. Facts only, no judgments.
- `src/ombuds/features/claims_triage/verticals/airline/rules.py` — `evaluate()`: scope check (Art. 3) → extraordinary-circumstances exemption (Art. 5(3)) → delay threshold (Art. 7, *Sturgeon*) → cancellation-notice exemption (Art. 5(1)(c)) → compensation tier by distance (Art. 7(1)) → reroute reduction (Art. 7(2)). First exemption found wins.
- `src/ombuds/domain/models/claim.py` — `EligibilityResult`: the vertical-agnostic output shape (`eligible`, `compensation_eur`, machine-readable `reasons`).
- `tests/unit/features/claims_triage/verticals/airline/test_rules.py` — boundary tests for every threshold (distance tiers, 3h delay cutoff, 7/14-day notice windows), built from one baseline `disruption(**overrides)` factory per `docs/code-style.md`.

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
- `scripts/compare_providers.py` — throwaway script, not part of the runtime provider layer (`platform/ai/providers/` is still stubbed). Calls Anthropic, OpenAI, and DeepSeek with the same EU261 prompt and prints text + latency + estimated cost side by side.

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
- `src/ombuds/platform/guardrails/approval_gate.py` — defines `GuardedAction` (which actions require approval) and `check_approval()`; currently denies every action unconditionally.
- `tests/unit/platform/guardrails/test_approval_gate.py` — pins that every `GuardedAction` is denied, parametrized so a new guarded action is covered automatically.

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
- `src/ombuds/platform/ai/schemas/tool_calls.py` — `ToolDefinition` (name, description, `args_model`), `ToolCall`, `ToolResult`: the provider-agnostic shape a tool-use turn is parsed into/out of, independent of any specific SDK's response type.
- `src/ombuds/platform/ai/tool_loop.py` — `ToolRegistry`: maps tool name → schema + handler; `dispatch()`/`dispatch_all()` validate arguments against the tool's `args_model` and run the handler, turning an unknown tool or a validation failure into an error `ToolResult` rather than an exception, so one bad call can't abort the rest of a turn.
- `src/ombuds/features/claims_triage/tools/check_eligibility.py` — read-only tool; reuses `FlightDisruption` as its own `args_model` and dispatches straight to `verticals/airline/rules.evaluate()`.
- `src/ombuds/features/claims_triage/tools/log_claim.py` — state-changing tool; `log_claim()` calls `approval_gate.check_approval()` before anything else and returns a denial result while the gate is the deny-all stub — persistence code isn't written yet since it's unreachable until W2.
- `tests/unit/platform/ai/test_tool_loop.py`, `tests/unit/features/claims_triage/tools/test_check_eligibility.py`, `tests/unit/features/claims_triage/tools/test_log_claim.py`.

**Notable libraries:** none new — same Pydantic/`StrEnum` patterns as the rules engine and approval gate.

**Decisions/trade-offs:** `check_eligibility`'s tool schema is `FlightDisruption` itself rather than a separate `CheckEligibilityArgs` wrapper — the tool takes exactly the rules engine's facts, so a second model would just duplicate the fields it's read-only over. `log_claim` raises `NotImplementedError` on the (currently unreachable) approved path rather than stubbing persistence, since there's no infrastructure layer yet to write to.
**Follow-up:** `issue_payment` still has no schema — deferred until it's wired up alongside `log_claim` in a later task; `tool_loop.ToolRegistry` isn't yet wired to a real provider response (that's the FastAPI `/triage` endpoint task next).

---

### Build FastAPI `/triage` endpoint (raw SDK, no framework)

**Week:** W1
**Goal:** Wire the existing `ToolRegistry` to a real provider turn and expose it as an HTTP endpoint — a raw `anthropic` SDK tool-use loop, not the LangGraph agent (that's a separate, later task).
**Source:** follow-up from the tool-schemas task

**Files & responsibilities:**
- `src/ombuds/platform/ai/providers/base.py` — `LLMProvider` Protocol (`run_turn`) and `ProviderTurn` (text, tool calls, stop reason, raw content), so `triage_use_case` isn't coupled to Anthropic's SDK types.
- `src/ombuds/platform/ai/providers/anthropic.py` — `AnthropicProvider.run_turn()`: converts `ToolDefinition`s to Anthropic's `input_schema` tool format, sends one `messages.create` call, and parses `tool_use`/`text` content blocks back into a `ProviderTurn`.
- `src/ombuds/config.py` — `load_prompt()` reads the active versioned prompt file per AGENTS.md's prompt-versioning rule; `CLAIMS_TRIAGE_PROMPT_VERSION` in `.env.example` records which version (`v2`) is live.
- `src/ombuds/platform/prompts/claims_triage/v2.txt` — filled in the previously-empty stub with the system prompt: always call `check_eligibility` rather than reasoning about EU261 itself, cite its reason codes, and expect `log_claim` may be denied by the approval gate.
- `src/ombuds/features/claims_triage/application/triage_use_case.py` — `run_triage()`: registers `check_eligibility`/`log_claim` on a `ToolRegistry`, loops `provider.run_turn()` → `registry.dispatch_all()` → feed `tool_result` blocks back, until the model stops requesting tools or `MAX_TOOL_TURNS` (8) is hit.
- `src/ombuds/features/claims_triage/api/schemas.py`, `api/routes.py` — `TriageRequest`/`TriageResponse` and `POST /claims/triage`, thin per AGENTS.md.
- `src/ombuds/api_app.py` — `create_app()` factory mounting the claims-triage router.
- `tests/unit/features/claims_triage/application/test_triage_use_case.py` — a fake `LLMProvider` (no real API calls) pins the no-tool-call, single-tool-call, unknown-tool, and max-turns-exceeded paths.
- `tests/unit/features/claims_triage/api/test_routes.py` — `TestClient` against the real app, `monkeypatch`ing `run_triage` so the route test doesn't depend on the use case's internals.

**Notable libraries:** FastAPI (`APIRouter`, `TestClient`) and its `httpx` dev dependency — both newly added to `pyproject.toml`.

**Decisions/trade-offs:** `LLMProvider.run_turn()` takes provider-native message dicts and returns a provider-specific `content` blob that's only ever replayed back into that same provider's next call — full provider-agnosticism across the message history was deferred since only Anthropic is wired up; `OpenAIProvider`/`fallback.py` stay stubs. `run_triage()` takes `provider` as an optional keyword so tests can inject a fake without a mocking framework.
**Follow-up:** streaming (SSE), structured-output retry/repair, and retries/backoff/fallback-model are their own W1 tasks next; a thorough unit-test pass over the tool-calling parser + endpoint (edge cases, malformed provider output) is the very next checklist item.

---

### Write unit tests for tool-calling parser + endpoint

**Week:** W1
**Goal:** Close edge-case gaps left after the FastAPI `/triage` task — the schemas, dispatch loop, and route had only happy-path coverage.
**Source:** follow-up from the FastAPI `/triage` endpoint task

**Files & responsibilities:**
- `tests/unit/platform/ai/test_tool_calls.py` (new) — `ToolDefinition.input_schema()` produces valid JSON Schema for its `args_model`; `ToolCall` is frozen (assignment raises); `ToolResult.is_error` defaults to `False`.
- `tests/unit/platform/ai/test_tool_loop.py` — added: `dispatch_all` doesn't abort the batch after one call fails (an unknown-tool error alongside a successful call in the same list); `definitions()` returns every registered `ToolDefinition`.
- `tests/unit/features/claims_triage/api/test_routes.py` — added: a request missing `claim_text` entirely (not just empty) returns 422; a non-empty `tool_results` tuple round-trips through JSON correctly; an unhandled exception from `run_triage` (e.g. the `MAX_TOOL_TURNS`-exceeded `RuntimeError`) propagates rather than being silently swallowed.

**Notable libraries:** none new — same pytest/`monkeypatch`/`TestClient` patterns as the existing route tests.

**Decisions/trade-offs:** the max-turns-exceeded `RuntimeError` is asserted to propagate as-is (via `pytest.raises`) rather than expecting a translated 500 response — the route currently has no exception handler, so this test documents current behavior rather than asserting a design that doesn't exist yet.
**Follow-up:** if `routes.py` later gets an explicit exception handler mapping use-case errors to a specific HTTP status, update this propagation test to assert on the response instead.

---

### Implement streaming (SSE) + buffered JSON parsing

**Week:** W1
**Goal:** Stream the triage answer and tool calls to the client as they happen instead of blocking until the whole tool-use loop finishes, and correctly assemble a tool call's arguments from the partial JSON fragments a streaming provider sends them in.
**Source:** follow-up from the FastAPI `/triage` endpoint task

**Files & responsibilities:**
- `src/ombuds/platform/ai/streaming.py` — `StreamEvent` union (`TextDelta`, `ToolCallDelta`, `ToolResultEvent`, `TurnDone`) that any provider's stream is normalized to; `JSONBuffer` accumulates one tool call's `input_json_delta` fragments (keyed by call id) and parses them into a dict once that content block closes.
- `src/ombuds/platform/ai/providers/base.py` — `LLMProvider` Protocol gains `stream_turn()` alongside the existing `run_turn()`, returning `Iterator[StreamEvent]`.
- `src/ombuds/platform/ai/providers/anthropic.py` — `AnthropicProvider.stream_turn()` uses `client.messages.stream()`, yielding `TextDelta`/`ToolCallDelta` as raw SDK events arrive, then a final `TurnDone` built from `stream.get_final_message()` (not the accumulated deltas) so it matches `run_turn()`'s output exactly regardless of chunking.
- `src/ombuds/features/claims_triage/application/triage_use_case.py` — `stream_triage()`: the same tool-use loop as `run_triage()`, but yields every `StreamEvent` from each turn plus a `ToolResultEvent` per dispatched tool call, instead of returning one final `TriageResult`.
- `src/ombuds/features/claims_triage/api/routes.py` — `POST /claims/triage/stream`: `StreamingResponse` over `text/event-stream`, formatting each `StreamEvent` as one `data: <json>\n\n` frame. The original blocking `POST /claims/triage` is unchanged and kept alongside it.
- `tests/unit/platform/ai/test_streaming.py` (new) — `JSONBuffer` fragment assembly, independent tracking per call id, and the malformed/non-object-JSON error paths.
- `tests/unit/features/claims_triage/application/test_triage_use_case.py` — `_FakeProvider.stream_turn()` added so `stream_triage()` can be tested against the same fixtures as `run_triage()`, without a real API call.
- `tests/unit/features/claims_triage/api/test_routes.py` — SSE frame shape for the streaming endpoint, via `monkeypatch`ing `stream_triage` the same way `run_triage` is monkeypatched elsewhere.

**Notable libraries:** `anthropic`'s `messages.stream()` context manager (`MessageStreamManager`) and its raw event types (`content_block_start`/`_delta`/`_stop`) — distinct from the `messages.create()` path `run_turn()` uses.

**Decisions/trade-offs:** `stream_turn()`'s final `TurnDone` is rebuilt from `get_final_message()` rather than trusted to the deltas accumulated during the loop, so a provider-SDK quirk in delta chunking can't silently diverge the streamed result from what `run_turn()` would have returned for the same request. No unit test mocks the raw Anthropic SDK stream events directly (there's no existing precedent for that in this codebase, and the SDK's event types are a lot of surface to fake) — coverage instead treats `LLMProvider.stream_turn()` as the tested boundary, same as `run_turn()`/`ProviderTurn` today. Why the endpoint is SSE rather than a WebSocket is recorded in [ADR-0007](decisions/0007-sse-over-websockets-for-triage-streaming.md).
**Follow-up:** structured-output validation with retry/repair, and retries/backoff/fallback-model, are still open W1 tasks; a streaming path adds a new failure mode worth covering there (a stream that drops mid-tool-call).

---

### Add structured output validation with Pydantic + retry/repair

**Week:** W1
**Goal:** Stop trusting the model's final reply as free-form text once it has a decision — force it into a validated `TriageDecision` shape, and give it a chance to fix its own mistake instead of failing the whole triage the first time it emits malformed JSON.

**Files & responsibilities:**
- `src/ombuds/platform/ai/schemas/structured_output.py` (new) — `parse_structured_output(text, schema)`: extracts the outermost `{...}` span from a reply (models wrap JSON in prose or a ```json fence even when told not to), `json.loads`s it, then `schema.model_validate`s it. Both failure modes raise one `StructuredOutputError` with a message written to be resent to the model verbatim.
- `src/ombuds/features/claims_triage/application/decision.py` (new) — `TriageDecision`: the required final shape (`eligible`, `compensation_amount_eur`, `reason_codes`, `explanation`).
- `src/ombuds/platform/prompts/claims_triage/v3.txt` (new, now active) — same rules as v2, plus a "final answer format" section telling the model to reply with only that JSON object once it has a decision, and to resend a corrected object if told its JSON didn't validate. Plain-text replies (e.g. asking the passenger for a missing fact) are still allowed.
- `src/ombuds/features/claims_triage/application/triage_use_case.py` — `run_triage()`: a final reply with no `{` in it is passed through unchanged as a plain-text answer (`decision=None`); one that contains `{` but fails to parse/validate triggers a repair turn (the validation error appended as the next user message) up to `MAX_REPAIR_ATTEMPTS` (2), after which `StructuredOutputError` propagates instead of being swallowed. `TriageResult` gained a `decision: TriageDecision | None` field.
- `src/ombuds/features/claims_triage/api/schemas.py`, `api/routes.py` — `TriageResponse` and `POST /claims/triage` now surface `decision` alongside `answer`.
- `tests/unit/platform/ai/test_structured_output.py` (new) — clean JSON, JSON-in-prose extraction, no-JSON-object / malformed-JSON / schema-validation-failure error paths.
- `tests/unit/features/claims_triage/application/test_triage_use_case.py` — added: a plain-text final reply still returns `decision=None`; an invalid-then-valid JSON pair proves the repair loop recovers; exhausting `MAX_REPAIR_ATTEMPTS` raises `StructuredOutputError`.
- `tests/unit/features/claims_triage/api/test_routes.py` — updated fixtures to include `decision` in both the request and the serialized response.

**Notable libraries:** `pydantic.ValidationError` (surfaced as the repair-prompt text) and `typing.TypeVar` (`parse_structured_output` is generic over the schema so callers get back the concrete type they asked for, not a bare `BaseModel`) — see glossary.

**Decisions/trade-offs:** why prompted JSON + client-side repair was chosen over native structured-output enforcement is recorded in [ADR-0005](decisions/0005-prompted-json-with-repair-over-native-structured-output.md). `stream_triage()`/SSE was deliberately left unchanged: doing the same validation there would need a feature-specific event type inside `platform/ai/streaming.py`, which would break the `platform` → `features` import-direction rule in `AGENTS.md` (platform code can't know about a feature's `TriageDecision`). Bumped the active prompt straight to v3 rather than gating it behind `evals/` per `AGENTS.md`'s prompt-versioning rule, since `evals/run_evals.py` is still a no-op placeholder — there's nothing to gate against yet.
**Follow-up:** if `evals/` gets built out, re-validate v3 against it properly rather than treating this bump as final; `stream_triage()` still has no structured-output validation on its final turn.
**Correction (pre-W2 hardening, 2026-09-27):** this task's validation was shape-only — a reply that parsed as a valid `TriageDecision` was accepted even if it disagreed with `check_eligibility`'s actual result, or if `check_eligibility` was never called (W1 review finding F-01; the README's core claim, "the LLM never becomes the source of truth for the claim's outcome", was not actually true of the returned decision). Added `verify_decision()` in `application/decision.py`, checked against the latest successful `check_eligibility` result through the same repair loop this task built, and reworked `log_claim`'s arguments to take flight facts rather than an eligibility judgment so a model-authored `EligibilityResult` can never reach it either. Bumped the active prompt to v4 (same eval-gate caveat as v3's bump above — `evals/run_evals.py` is still a no-op placeholder). See ADR-0005's updated Consequences.

---

### Add retries/backoff, timeouts, fallback model, idempotency

**Week:** W1
**Goal:** Stop treating the Anthropic call as always-succeeds — add timeouts and backoff-retries for transient failures, fail over to a cheaper/secondary model if the primary keeps failing, and make retried requests idempotent so a retry (ours or the SDK's own) can't double-execute the same logical call.

**Files & responsibilities:**
- `src/ombuds/platform/ai/providers/anthropic.py` — `AnthropicProvider.__init__` now builds its `anthropic.Anthropic` client with `timeout`/`max_retries` (defaults 30s / 2 retries), delegating transient connection/429/5xx handling to the SDK's own exponential backoff instead of hand-rolling it. Added `_idempotency_key()`: a sha256 of `(model, system, messages, tool names)` sent as the `idempotency-key` header on both `run_turn()` and `stream_turn()`, so the same logical request (SDK retry, or a same-model retry from the layer below) dedupes server-side instead of re-running; a new turn (grown conversation) naturally gets a new key.
- `src/ombuds/platform/ai/providers/fallback.py` — `FallbackProvider`: wraps a `primary` and `fallback` `LLMProvider`, retrying `run_turn()` against `primary` with its own exponential backoff (`max_attempts`, default 3) before failing over to `fallback` entirely. `stream_turn()` does the same, but only fails over if the primary errors *before* any event has reached the caller — once output has started, a mid-stream failure is re-raised as-is rather than risking duplicate/replayed output. Also provides `build_default_provider()`, composing `ANTHROPIC_MODEL` as primary and `ANTHROPIC_FALLBACK_MODEL` as fallback from `config.py`.
- `src/ombuds/config.py`, `.env.example` — new `ANTHROPIC_FALLBACK_MODEL` (default `claude-haiku-4-5`), `ANTHROPIC_TIMEOUT_SECONDS` (30), `ANTHROPIC_MAX_RETRIES` (2).
- `src/ombuds/features/claims_triage/application/triage_use_case.py` — `run_triage()`/`stream_triage()` now default to `build_default_provider()` instead of a bare `AnthropicProvider()`, so triage gets retry/fallback behavior without callers changing anything (tests still inject `_FakeProvider` directly).
- `tests/unit/platform/ai/providers/test_fallback.py` (new) — primary succeeds without retry; primary recovers within its retry budget; primary exhausts retries and `fallback` answers instead; a streaming failure before any output falls back; a streaming failure after output has started is re-raised, not swallowed. Uses an injectable `sleep` callable so backoff delays don't slow the test suite.
- `tests/unit/platform/ai/providers/test_anthropic.py` (new) — `_idempotency_key()` is stable for an identical request, changes once the conversation grows, and changes with model.

**Notable libraries:** `anthropic.Anthropic(timeout=, max_retries=)` — the SDK's built-in httpx-based timeout/retry handling; no new third-party retry/backoff library was added since one layer's needs (client-level transient-error retry) were already covered by the SDK, and the other (cross-model fallback) needed custom fallover logic a generic decorator wouldn't express well.

**Decisions/trade-offs:** why the work is split into two resilience layers (SDK-level retries vs. `FallbackProvider`'s model fallover) instead of one retry library, and why `FallbackProvider` catches bare `Exception` (the one intentional exception to the no-bare-except rule in `docs/code-style.md`), is recorded in [ADR-0006](decisions/0006-two-layer-resilience-over-a-retry-library.md). Idempotency is scoped to the Anthropic provider's own header (derived from request content, not a random key), rather than a cross-provider idempotency scheme, since retrying against `fallback` is already a different model/request and doesn't need to dedupe against `primary`'s attempts.
**Follow-up:** `OpenAIProvider`/`fallback.py`'s provider-agnosticism is still untested against a live second provider (only two `AnthropicProvider` instances are composed today, since `OpenAIProvider` remains a stub); wiring OpenAI in as the fallback instead of a cheaper Anthropic model is a natural next step once that provider is implemented.
**Correction (pre-W2 hardening, 2026-09-27):** the `idempotency-key` header this task added was checked against the official Messages API reference and confirmed unsupported — Anthropic's Messages API does not document idempotency-key handling the way Stripe's API does, so `_idempotency_key()` and its header were doing nothing server-side. Removed from `anthropic.py` along with its tests. Idempotency belongs at the point where a duplicate call would actually cause harm — the state-changing tools (`log_claim`, `issue_payment`) landing in W2, keyed by `claim_id` — not at the LLM-call layer, which has no side effects to double-execute. See W1 review finding F-04.

---

### Rebuild tool-calling loop in LangGraph

**Week:** W2
**Goal:** Replace the W1 hand-rolled `for`-loop tool-use orchestration with an explicit LangGraph `StateGraph`, so the agentic loop is graph-native and later W2 nodes (classify/retrieve/decide/escalate_retry) have a graph to hang off of.
**Source:** `ombuds_build_tasks.md` Week 2 checklist

**Files & responsibilities:**
- `src/ombuds/features/claims_triage/agent/state.py` — `AgentState`: the `TypedDict` threaded through every node (messages, accumulated `tool_results`, `pending_tool_calls`/`text` staging the latest model turn, `turns`/`repair_attempts` counters, `answer`/`decision`, `done`).
- `src/ombuds/features/claims_triage/agent/graph.py` — `build_triage_graph(provider, registry, system)`: compiles a 3-node graph — `call_model` (one provider turn) → routes to `dispatch_tools` (runs `ToolRegistry.dispatch_all`, loops back to `call_model`) or `finalize` (validates/verifies the final reply, either returning `answer`/`decision` or looping back to `call_model` with a repair message). Also hosts `tool_result_message()`, `_repair_message()`, `_parse_final_turn()` — moved here from `triage_use_case.py` since the loop now lives in this module.
- `src/ombuds/features/claims_triage/application/triage_use_case.py` — `run_triage()` now builds and `.invoke()`s the compiled graph instead of a manual loop; same `TriageResult` contract, same `MAX_TOOL_TURNS`/`MAX_REPAIR_ATTEMPTS` bounds (now re-exported from `agent/graph.py`). `stream_triage()` is unchanged (streaming isn't threaded through the graph yet) but now imports `tool_result_message()` instead of duplicating it.
- `tests/unit/features/claims_triage/application/test_triage_use_case.py` — unchanged; passes against the graph-backed `run_triage()` with no test edits, confirming behavior parity (tool dispatch, repair-on-bad-JSON, repair-on-`verify_decision`-mismatch, unknown-tool error, non-convergence after `MAX_TOOL_TURNS`).
- `pyproject.toml` — added `langgraph>=0.2`.

**Notable libraries:** LangGraph (`StateGraph`, `CompiledStateGraph`, `END`) — see glossary.

**Decisions/trade-offs:** `stream_triage()` was deliberately left on the old manual loop rather than also rebuilt on the graph — streaming events (`TextDelta`/`ToolCallDelta`/`TurnDone`) aren't yet a first-class graph concept here, and folding them in would have doubled this task's scope for no behavior change; picked up as a later W2/W3 follow-up if streaming needs the same node structure. The tool-loop nodes (`call_model`/`dispatch_tools`/`finalize`) were written directly in `agent/graph.py` rather than split across `agent/nodes/*.py` (`classify.py`/`decide.py`/`retrieve.py`/`escalate_retry.py` per `AGENTS.md`'s layout) — those stubs are for the broader classify→retrieve→decide pipeline, which doesn't exist yet; wiring the tool loop into that node package is deferred to whichever task builds that pipeline, rather than guessing its shape now.
**Follow-up:** `agent/nodes/classify.py`, `retrieve.py`, `decide.py`, `escalate_retry.py` remain empty stubs — not wired into this graph. `stream_triage()` still bypasses the graph.

---

Library/framework/stdlib-concept entries live in [`ombuds_build_glossary.md`](ombuds_build_glossary.md) — append there, not here, whenever a summary's **Notable libraries** introduces something not already listed.
