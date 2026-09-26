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

Library/framework/stdlib-concept entries live in [`ombuds_build_glossary.md`](ombuds_build_glossary.md) — append there, not here, whenever a summary's **Notable libraries** introduces something not already listed.
