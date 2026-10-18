# W1 Review & Pre-W2 Plan

_Reviewed 2026-09-26 against `main` @ `112dd93` (PR #10 merged). `make test` → lint clean, mypy strict clean, 78/78 unit tests pass._

---

## 1. Current Project State

**Architecture.** Feature-sliced layout per ADR-0002: `domain/` → `platform/` ← `features/claims_triage/`, with `api_app.py` as the only composition root that exists so far. I grepped the import graph and the layering holds: nothing in `platform/` or `domain/` imports from `features/`.

**What runs today.** A raw Anthropic tool-use loop with no framework (`application/triage_use_case.py`), exposed as:

- `POST /claims/triage`: sync. Loops for up to 8 tool turns, then validates the final reply against `TriageDecision` and repairs it up to 2 times.
- `POST /claims/triage/stream`: SSE. Same loop, streams events, **no** decision validation.

Behind the loop are:

- two tools, `check_eligibility` (read-only, delegates to `verticals/airline/rules.py`) and `log_claim` (state-changing, always denied by the deny-all `approval_gate` stub);
- a provider layer `LLMProvider` (a Protocol) implemented by `AnthropicProvider` and `FallbackProvider` (primary model → fallback model);
- versioned prompts, with `v3` live.

**Technologies.** Python 3.11, FastAPI (sync handlers), Pydantic v2 (frozen models throughout), `anthropic` SDK, uv, ruff, mypy `--strict` with the pydantic plugin, pytest, pre-commit.

**Not built yet (scaffold only, one-line docstring files).** LangGraph agent, RAG, MCP, OPA/Rego, PII/injection guardrails, infrastructure, observability, evals (`evals/datasets/airline_claims.jsonl` is empty), Docker. This matches the roadmap and needs no action.

**Overall.** The codebase is small (~900 LOC of real source), consistent, and noticeably better disciplined than a typical 1-week prototype. Most of what I found is about **a few specific places where behaviour doesn't match what the code, docs or README claim**. It is not about structure. The structure is sound and I'm not recommending any reorganisation.

---

## 2. W1 Assessment

| W1 task | Implemented in | Verdict |
|---|---|---|
| Folder structure | `src/ombuds/**`, ADR-0002/0003 | ✅ Sound. One layering contradiction, in ADR-0003 about MCP bindings (F-06) |
| EU261 rules engine + tests | `verticals/airline/rules.py`, `test_rules.py` | ✅ Best module in the repo: pure, cites the regulation, has named thresholds, reason codes, and boundary-parametrised tests |
| Call OpenAI & Anthropic directly | `scripts/compare_providers.py` | ✅ Correctly kept out of runtime code. Small stale docstring |
| Deny-all approval gate | `platform/guardrails/approval_gate.py`, `tools/log_claim.py` | ✅ Enforced inside the tool, not in the prompt. But the *arguments* reaching the gate are LLM-authored (F-01) |
| Tool schemas + tool-use loop | `platform/ai/tool_loop.py`, `schemas/tool_calls.py`, `tools/*` | ✅ Clean registry. Bad args and unknown tools become error results. Handler-exception contract is wrong (F-05) |
| FastAPI `/triage` | `api/routes.py`, `api/schemas.py` | ✅ Thin, delegates to application. Errors surface as raw 500s (F-10) |
| Unit tests for parser + endpoint | `tests/unit/**` | ✅ Good naming, fakes via Protocol, no network. One real gap: the Anthropic adapter itself (F-12) |
| Streaming (SSE) + buffered JSON | `platform/ai/streaming.py`, `AnthropicProvider.stream_turn` | ⚠️ Works, but diverges from `/triage`: no decision validation or repair (F-07) |
| Structured output + retry/repair | `schemas/structured_output.py`, `application/decision.py` | ⚠️ Validates the *shape*, not the *truth*. The decision isn't checked against the rules engine's result (F-01) |
| Retries/backoff, timeouts, fallback, idempotency | `providers/anthropic.py`, `providers/fallback.py`, `config.py` | ❌ Three real defects: timeout and retry config never reach the client (F-02), retries aren't classified and multiply (F-03), and the idempotency header most likely does nothing (F-04) |

**Consistency with the project's own standards.** Mostly high: docstrings, frozen models, `StrEnum`, units in names, pure rules, and one test module per source module. The deviations that matter:

- **`docs/code-style.md` "no `except Exception`"** was waived for `FallbackProvider`. The waiver's reasoning ("can't enumerate every provider's exceptions") has a better answer, which F-03 describes.
- **README's core claim**, *"The LLM … never becomes the source of truth for the claim's outcome"*, is currently not true of either the returned `TriageDecision` or `log_claim`'s arguments (F-01).
- **AGENTS.md's prompt-versioning gate** ("must run clean against evals before becoming active") was skipped for v3. The skip was acknowledged in the task summary, and it was unavoidable because the evals don't exist yet.

---

## 3. Findings

Ordered by priority.

### F-01: The LLM is the source of truth for eligibility and amount (both in the returned decision and in `log_claim`)
- **Area:** Domain correctness / governance
- **Current situation:**
  - `LogClaimArgs.eligibility: EligibilityResult` ([log_claim.py:10-16](../../src/ombuds/features/claims_triage/tools/log_claim.py#L10-L16)) is filled in **by the model** as tool arguments. The docstring says it is "`check_eligibility`'s prior output, not recomputed", but nothing verifies that.
  - `TriageDecision.eligible` and `compensation_amount_eur` ([decision.py:15-18](../../src/ombuds/features/claims_triage/application/decision.py#L15-L18)) are model-authored JSON that is only schema-validated ([triage_use_case.py:45-53](../../src/ombuds/features/claims_triage/application/triage_use_case.py#L45-L53)).
  - A decision is accepted even if `check_eligibility` was never called or returned something different.
  - `reason_codes` are free strings. The unit test itself uses `"EU261_ART7"`, which is not a `Reason` value, and it passes.
  - `compensation_amount_eur: float` vs `EligibilityResult.compensation_eur: int`: two types for the same fact.
- **Problem / risk:** This is the exact failure the project exists to prevent. W2 replaces the deny-all stub with a real approval gate. From then on, a human approver (and later `issue_payment`) would be shown a number the model typed, which may be hallucinated, transcribed wrong, or produced by prompt injection in `claim_text`. Human review mitigates this but doesn't fix it: the reviewer is shown fabricated data presented as a rules-engine output.
- **Recommended change:**
  1. `log_claim` takes the **facts** (`claim_id` + `FlightDisruption`) and calls `rules.evaluate()` itself. The rules are pure and cheap, so recomputing is simpler than any proof-of-provenance scheme.
  2. After `TriageDecision` parses, check it against the most recent successful `check_eligibility` result in `tool_results`:
     - `eligible` and the amount must match;
     - `reason_codes` must equal the result's `reasons`;
     - "no eligibility check was run" is a failure.

     Feed any mismatch into the **existing** repair loop as a repair message. Put the check in `application/decision.py`.
  3. Make `compensation_amount_eur` an `int`, to match the domain.
- **Reason:** The README's core architectural claim is currently false. The fix is local (two modules) and reuses the existing repair machinery.
- **Priority:** Critical · **Complexity:** Medium · **Must fix before W2:** Yes

### F-02: `ANTHROPIC_TIMEOUT_SECONDS` / `ANTHROPIC_MAX_RETRIES` are dead config
- **Area:** Configuration
- **Current situation:** [config.py:14-15](../../src/ombuds/config.py#L14-L15) reads both variables and `.env.example` documents them. But `build_default_provider()` ([fallback.py:114-122](../../src/ombuds/platform/ai/providers/fallback.py#L114-L122)) passes only `model=`, so `AnthropicProvider` always uses its hard-coded `DEFAULT_TIMEOUT_SECONDS = 30.0` / `DEFAULT_MAX_RETRIES = 2` ([anthropic.py:13-15](../../src/ombuds/platform/ai/providers/anthropic.py#L13-L15)). `DEFAULT_MODEL` is also defined twice: in `config.py` and in `anthropic.py`.
- **Problem / risk:** Operators tune a setting that has no effect. This is a silent correctness bug in a W1 deliverable.
- **Recommended change:** Pass `timeout=` / `max_retries=` from config in `build_default_provider()`. Drop `DEFAULT_MODEL` from `anthropic.py` and make `model` a required constructor argument.
- **Reason:** A trivial fix for a real bug.
- **Priority:** High · **Complexity:** Small · **Must fix before W2:** Yes

### F-03: `FallbackProvider` retries everything, and its retries multiply with the SDK's own retries
- **Area:** Error handling / resilience / cost
- **Current situation:** `FallbackProvider` catches `Exception` ([fallback.py:55, 74, 97](../../src/ombuds/platform/ai/providers/fallback.py#L55)) and retries the primary 3×, on top of the SDK client that already retries 2× (the SDK retries connection errors, 408, 409, 429 and 5xx).
- **Problem / risk:**
  - **Non-retryable failures are retried and then re-run on the fallback model.** This covers 400 (for example a malformed tool schema), 401/403 (a bad key), 404 (a bad model id), and even a `TypeError` or `KeyError` in our own response parsing. The result is 4 useless calls plus a misleading "falling back" warning, and a programming bug gets reported as provider flakiness.
  - **Amplification:** up to 3 × (1 + 2) = 9 HTTP attempts at a 30 s timeout, so about 4.5 min per turn before fallback. With up to 8 turns plus repairs, one request can hang for tens of minutes while holding a threadpool worker.
- **Recommended change:**
  1. `AnthropicProvider` translates SDK errors **at its own boundary** into one platform exception, e.g. `ProviderUnavailableError` in `platform/ai/providers/base.py`. It should cover `APIConnectionError`, `APITimeoutError`, `RateLimitError`, `InternalServerError` and 5xx/529.
  2. Everything else propagates unchanged.
  3. `FallbackProvider` catches only `ProviderUnavailableError`, which removes the documented exception to the no-`except Exception` rule.
  4. Since the SDK already backs off, set `FallbackProvider`'s default `max_attempts` to 1 (fail over straight away). Keep the parameter.
- **Reason:** The provider-agnostic layer doesn't need to enumerate SDK exceptions. Each adapter translates its own, which is the standard Ports and Adapters approach. It fixes cost, latency and diagnosability in one change, and the LangGraph rebuild in W2 will sit on top of this layer.
- **Priority:** High · **Complexity:** Small · **Must fix before W2:** Yes

### F-04: The `idempotency-key` header on Messages API calls most likely does nothing, and it sits on the wrong layer
- **Area:** API design / correctness of claims
- **Current situation:** `_idempotency_key()` ([anthropic.py:19-32](../../src/ombuds/platform/ai/providers/anthropic.py#L19-L32)) hashes the model, system prompt, messages and tool names, and sends the result as `idempotency-key` on every call. The docstring and the task summary state that "Anthropic's Messages API honors an `idempotency-key` header the same way Stripe's does."
- **Problem / risk:**
  - I found no documentation of an idempotency header for the Messages API. **This needs verifying**, but if it is unsupported, the code is dead and the docstring makes a false claim about a W1 deliverable.
  - Even if the header were honoured, LLM generation has no side effects, so deduplicating it only saves tokens. A key derived from content would also collide for two different users who submit the same claim text.
  - Idempotency actually matters for **state-changing tools** (`log_claim`, `issue_payment`, keyed by `claim_id`), which arrive in W2 and currently have none.
- **Recommended change:** Check the API reference.
  - **If the header isn't supported:** remove it and its 3 tests.
  - **Either way:** move the idempotency requirement into the W2 approval-gate and `issue_payment` work (a unique `claim_id`-based key at the persistence layer), and correct the task summary.
- **Reason:** It removes a misleading mechanism and points idempotency at the place where a duplicate costs real money.
- **Priority:** Medium · **Complexity:** Small · **Must fix before W2:** Yes (it's cheap, and W2 designs the real idempotency)

### F-05: `ToolRegistry.dispatch` claims "never raises", but handler exceptions escape, and W2's first approval will hit that
- **Area:** Error handling / interface contract
- **Current situation:** [tool_loop.py:32-49](../../src/ombuds/platform/ai/tool_loop.py#L32-L49) catches only `ValidationError`, so `handler(args)` can raise. `log_claim` raises `NotImplementedError` as soon as approval returns `approved=True` ([log_claim.py:41-44](../../src/ombuds/features/claims_triage/tools/log_claim.py#L41-L44)). The handler adapters use `assert isinstance(...)` ([triage_use_case.py:56-63](../../src/ombuds/features/claims_triage/application/triage_use_case.py#L56-L63)), and asserts are stripped under `python -O`.
- **Problem / risk:** The first approval granted in W2 turns into a 500 that aborts the whole triage. W2 also adds a second consumer of the registry (MCP), which needs a defined answer to "what does a failing tool return".
- **Recommended change:**
  - Define `ToolExecutionError` in `domain/errors.py` (currently an empty file). Tools raise it for expected failures, such as persistence unavailable.
  - `dispatch` converts `ToolExecutionError` into an `is_error=True` `ToolResult`. Genuinely unexpected exceptions still propagate, so bugs stay loud.
  - Fix the docstring.
  - Replace the `assert` with an explicit `TypeError`, or better, move the typed adapters next to the tools (see F-06).
- **Reason:** It pins the contract once, before two consumers depend on it. It also follows code-style's "domain errors in `errors.py`, catch specific exceptions".
- **Priority:** Medium · **Complexity:** Small · **Must fix before W2:** Yes

### F-06: The tool catalogue has no home, and ADR-0003 contradicts ADR-0002 about where MCP bindings live
- **Area:** Architecture / dependency direction
- **Current situation:**
  - The list of registered tools lives privately inside the use case (`_build_registry`, [triage_use_case.py:56-70](../../src/ombuds/features/claims_triage/application/triage_use_case.py#L56-L70)).
  - ADR-0003 says "`platform/mcp/tool_bindings.py` is the single place that wraps feature tools (`features/claims_triage/tools/`)". That means `platform` importing `features`, which ADR-0002 and AGENTS.md forbid ("only composition roots wire features into platform").
- **Problem / risk:** W2 tasks 2 and 3 (MCP server, LangGraph over MCP) need the same tool set in up to three places. Without a decision now, the natural path either duplicates the tool list or breaks the import rule on day 1 of W2.
- **Recommended change:**
  - Move the catalogue (definitions plus typed handler adapters) to `features/claims_triage/tools/__init__.py`, exposed as `build_tool_registry() -> ToolRegistry`.
  - `platform/mcp/tool_bindings.py` stays generic: it turns a `ToolRegistry` into MCP tools.
  - `platform/mcp/server.py` is a composition root, so it may import the feature's `build_tool_registry()`.
  - Amend the one consequence line in ADR-0003. This is a clarification, not a new ADR.
- **Reason:** It resolves a documented contradiction before code is written against it, and gives one source of truth for the tool set.
- **Priority:** High · **Complexity:** Small · **Must fix before W2:** Yes

### F-07: `/triage/stream` skips decision validation and repair, so the two endpoints return different contracts
- **Area:** API consistency
- **Current situation:** `stream_triage` ([triage_use_case.py:121-164](../../src/ombuds/features/claims_triage/application/triage_use_case.py#L121-L164)) returns on the first turn with no tool calls. The client receives raw JSON text inside `turn_done`, gets no `decision`, and there is no repair step. The task summary justifies this as "platform can't know `TriageDecision`", but `stream_triage` is in `features/` and could yield a feature-level event (e.g. `TriageStreamEvent = StreamEvent | DecisionEvent`) without touching `platform/`. The two loops also duplicate the turn cap and the tool-result message construction.
- **Problem / risk:** Clients of the streaming endpoint get unvalidated verdicts, and F-01's consistency check would apply to only one path.
- **Recommended change:** **Don't fix this in the raw loop**, because W2 task 1 replaces it with LangGraph. Instead, make it an acceptance criterion of that task: one graph whose sync and streaming entry points share the same finalise → validate → verify (F-01) → repair step, and emit a `decision` SSE frame. The existing `test_triage_use_case.py` scenarios become the parity suite for the new graph.
- **Reason:** Fixing it now would mean rewriting code that is about to be deleted.
- **Priority:** Medium · **Complexity:** Medium · **Must fix before W2:** No (W2 acceptance criterion)

### F-08: The provider abstraction leaks Anthropic's wire format into the feature layer
- **Area:** Abstraction / extensibility
- **Current situation:**
  - The use case builds Anthropic-shaped `{"type": "tool_result", "tool_use_id": ...}` messages itself ([triage_use_case.py:103-116](../../src/ombuds/features/claims_triage/application/triage_use_case.py#L103-L116)).
  - `messages` is `list[dict[str, object]]` in "provider-native wire format".
  - `FallbackProvider`'s docstring says primary and fallback "may be entirely different SDKs". That can't work: the history is Anthropic-shaped, and the primary's `turn.content` is replayed to the fallback.
  - A separate concern to verify: Sonnet 5 runs adaptive thinking by default when `thinking` is omitted, so the primary's content may include thinking blocks, which would then be replayed to Haiku on fallback.
- **Problem / risk:** It is harmless while every provider is Anthropic. It becomes a design decision the moment W2 defines `AgentState`.
- **Recommended change:**
  - **Now:** correct the `FallbackProvider` docstring so it says the fallback must be the same wire format. **Don't** build an OpenAI adapter or a neutral message model speculatively.
  - **At W2 start**, when designing `agent/state.py`, choose one of:
    - (a) the provider owns formatting via something like `provider.tool_results_message(results)`, or
    - (b) state holds neutral messages and each provider converts them.
  - Also confirm with one live call whether thinking blocks appear in `content`.
- **Reason:** A cheap correction now, with the real decision deferred to the point where it has a concrete consumer.
- **Priority:** Medium · **Complexity:** Small (docstring) · **Must fix before W2:** No (W2 design input)

### F-09: `MAX_TOKENS = 1024`, and `stop_reason` is never inspected
- **Area:** LLM integration correctness
- **Current situation:** [anthropic.py:16](../../src/ombuds/platform/ai/providers/anthropic.py#L16) sets 1024 max tokens, and the loop treats any turn without tool calls as final, whatever `stop_reason` is.
- **Problem / risk:** If adaptive thinking is on (see F-08), thinking tokens count against 1024, so a truncated reply is likely. A turn with `max_tokens` becomes either a pointless repair round-trip or, when the reply is prose, a truncated `answer` returned as final. `refusal` is handled the same way.
- **Recommended change:** Make `max_tokens` a config value with a realistic default (4–8k). In the loop, treat `stop_reason in {"max_tokens", "refusal"}` as an explicit failure (a typed error, and an escalation route in W2) rather than a final answer.
- **Priority:** Medium · **Complexity:** Small · **Must fix before W2:** No (fold into the W2 loop rebuild; the `MAX_TOKENS` change is a one-liner that can go in any time)

### F-10: No typed errors or HTTP mapping, and SSE failures drop silently
- **Area:** Error handling / API design
- **Current situation:**
  - `domain/errors.py` is empty.
  - Non-convergence raises `RuntimeError`, repair exhaustion raises `StructuredOutputError`, and provider failures raise SDK exceptions. All of them become bare 500s. `test_triage_endpoint_propagates_use_case_errors_as_a_server_error` pins that behaviour.
  - A failure after SSE has started just closes the stream with no error frame.
- **Problem / risk:** Clients can't tell "the model couldn't decide" (a business outcome that should escalate) from "the provider is down" (503) or a bug (500).
- **Recommended change:** Add typed errors (`TriageDidNotConverge`, `DecisionInvalid`) and FastAPI exception handlers in `api/`, plus an `{"type": "error"}` SSE frame. In W2, non-convergence should route to the escalation node rather than raise.
- **Priority:** Medium · **Complexity:** Small · **Must fix before W2:** No (natural fit with W2's "escalation/retry loop" task)

### F-11: No behavioural baseline exists before the loop is rewritten
- **Area:** Evaluation / AI engineering practice
- **Current situation:** `evals/datasets/airline_claims.jsonl` is empty and `run_evals.py` is a placeholder. Prompt v3 went live without the eval gate AGENTS.md requires (acknowledged).
- **Problem / risk:** W2 task 1 rewrites the orchestration, and with no baseline there is no evidence the LangGraph version behaves as well as the raw loop. Unit tests with fake providers can't catch prompt or model regressions.
- **Recommended change:** Build a small golden set: about 8–10 claims covering each `Reason` path plus one "missing facts" clarifying case. The expected values come from `rules.evaluate()`, not hand-written. Add a script that runs `run_triage` against the real API and reports decision agreement. Run it once now to record a baseline, and once after the LangGraph rebuild. The full eval task stays in W3.
- **Priority:** Medium · **Complexity:** Small–Medium · **Must fix before W2:** No, but it is the highest-value optional item

### F-12: Test gaps and hygiene
- **Area:** Testing
- **Current situation:**
  - `AnthropicProvider.run_turn` and `stream_turn` are untested. They contain the most intricate adapter code: block-index → call-id mapping, `JSONBuffer` integration, and `get_final_message` reconciliation. Only `_idempotency_key` is tested.
  - `test_eu261_rules.py` is an empty duplicate of `test_rules.py`.
  - `tests/unit/features/claims_triage/guardrails/` is an empty package with no `src` counterpart.
  - [test_tool_calls.py:25-34](../../tests/unit/platform/ai/test_tool_calls.py#L25-L34) uses `try/except Exception` instead of `pytest.raises(ValidationError)`.
- **Recommended change:**
  - Add adapter tests with a fake `anthropic.Anthropic` client that returns canned content blocks and stream events. This is also where F-03's error translation gets tested.
  - Delete the two empty placeholders.
  - Use `pytest.raises`.
- **Priority:** Medium (adapter tests) / Low (hygiene) · **Complexity:** Small · **Must fix before W2:** No, except the adapter error-translation tests, which ship with F-03

### F-13: Provider built per request inside the use case (hidden dependency)
- **Area:** Dependency injection / resource use
- **Current situation:**
  - `provider = provider or build_default_provider()` ([triage_use_case.py:79, 128](../../src/ombuds/features/claims_triage/application/triage_use_case.py#L79)) constructs two fresh `anthropic.Anthropic` clients, and so two HTTP connection pools, **per request**.
  - `build_default_provider` reads `ombuds.config` through a lazy import from inside `platform/`.
  - Route tests have to monkeypatch module attributes.
- **Problem / risk:** No connection reuse, and the wiring is hidden. W2's graph construction needs the provider too.
- **Recommended change:** Build the provider once in `create_app()` (on `app.state`, or through a `Depends`), and make `provider` a required argument of the use case or graph. Tests then use `app.dependency_overrides`.
- **Priority:** Medium · **Complexity:** Small · **Must fix before W2:** No (do it while building the LangGraph graph, which needs the same wiring)

### F-14: Minor: dependencies, input limits, stale docs
- **Area:** Dependency management / security / docs
- **Current situation and recommended change:**
  - `openai` is a runtime dependency but only `scripts/compare_providers.py` uses it. Move it to a `scripts` dependency group.
  - `claim_text` has no `max_length`, so there is no ceiling on token cost for one request across up to 8 turns and retries. Add a generous limit, e.g. 10k characters.
  - AGENTS.md says the prompts are "currently `v1.txt`, `v2.txt`". `v3` is live, and `v1.txt` is a one-line placeholder that would load as the whole system prompt if selected. Update the line.
  - The `compare_providers.py` docstring still says the provider layer is "still stubbed".
  - `config.py` runs `load_dotenv()` and `float()` at import time. That is fine for now; revisit with `pydantic-settings` when W3 adds the database configuration, not before.
- **Priority:** Low · **Complexity:** Small · **Must fix before W2:** No

### Deliberately *not* raised

- **Sync vs async:** sync FastAPI handlers run in the threadpool, and LangGraph supports sync execution. There's no concurrency requirement that justifies going async before W2.
- **Scaffold stub modules:** these are intended by the roadmap and aren't debt.
- **`ProviderTurn` / `TurnDone` field duplication:** cosmetic, and the streaming path is rewritten in W2.
- **`"{" in text` heuristic for detecting a JSON attempt:** a documented trade-off, and good enough given the prompt.
- **`.rego` and prompts living under `platform/`:** already accepted in ADR-0002 and AGENTS.md.

---

## 4. Required Refactoring Before W2

Listed in implementation order.

### T-1: Wire provider config and remove the duplicated default model (F-02)
- **Files:** `platform/ai/providers/fallback.py` (`build_default_provider`), `platform/ai/providers/anthropic.py`, `config.py`
- **Reason:** Documented settings currently have no effect.
- **Acceptance criteria:**
  - `ANTHROPIC_TIMEOUT_SECONDS` and `ANTHROPIC_MAX_RETRIES` reach both `AnthropicProvider` clients.
  - `AnthropicProvider` has no model default of its own.
  - A unit test asserts that the configured values are passed through, e.g. by monkeypatching `config` and inspecting the built providers.
- **Depends on:** nothing

### T-2: Classify retryable provider errors at the adapter boundary (F-03)
- **Files:** `platform/ai/providers/base.py` (new `ProviderUnavailableError`), `anthropic.py`, `fallback.py`, `docs/code-style.md` (remove the `except Exception` carve-out), new `tests/unit/platform/ai/providers/test_anthropic.py` cases, `test_fallback.py`
- **Reason:** Stops retrying non-retryable errors, stops the retries multiplying, and keeps bugs loud.
- **Acceptance criteria:**
  - `AnthropicProvider` raises `ProviderUnavailableError` (chained with `from exc`) for connection errors, timeouts, 429 and 5xx/529, and lets 4xx and all other exceptions propagate unchanged. This applies to both `run_turn` and `stream_turn`, and is tested with a fake client.
  - `FallbackProvider` catches only `ProviderUnavailableError`. There is a test that a `ValueError` from the primary propagates without calling the fallback.
  - The default `max_attempts` is 1, and the parameter is kept.
  - There is no `except Exception` left in `src/`.
- **Depends on:** T-1 (same files; do them in sequence)

### T-3: Resolve the idempotency header (F-04)
- **Files:** `platform/ai/providers/anthropic.py`, `tests/unit/platform/ai/providers/test_anthropic.py`, `docs/progress/task_summaries.md`, `docs/progress/tasks.md` (W2 approval-gate task description)
- **Reason:** It removes a mechanism that probably has no effect, and records where idempotency is really needed.
- **Acceptance criteria:**
  - Support for the header in the Messages API is confirmed or ruled out against the official API reference, and the outcome is noted in the task summary.
  - If unsupported, `_idempotency_key` and its tests are removed.
  - The W2 approval-gate / `issue_payment` task notes: "state-changing tools must be idempotent on `claim_id`".
- **Depends on:** T-2 (same file)

### T-4: Define the tool-execution error contract (F-05)
- **Files:** `domain/errors.py`, `platform/ai/tool_loop.py`, `features/claims_triage/tools/log_claim.py`, `tests/unit/platform/ai/test_tool_loop.py`
- **Reason:** W2's first real approval must not crash the triage, and MCP needs the same contract.
- **Acceptance criteria:**
  - `ToolExecutionError` exists in `domain/errors.py`.
  - `dispatch` turns it into an `is_error=True` result and still propagates other exceptions. Both behaviours are tested.
  - The docstring matches the behaviour.
  - `log_claim`'s approved branch raises `ToolExecutionError("persistence not implemented")` instead of `NotImplementedError`, so enabling the gate yields a tool error the model can explain rather than a 500.
- **Depends on:** nothing (can run in parallel with T-1 to T-3)

### T-5: Give the tool catalogue a home and fix ADR-0003's layering line (F-06)
- **Files:** `features/claims_triage/tools/__init__.py` (new `build_tool_registry()`, typed adapters without `assert`), `application/triage_use_case.py` (use it), `docs/decisions/0003-mcp-as-subpackage-not-service.md` (amend the consequence), `AGENTS.md` (the `mcp/` line)
- **Reason:** One tool set shared by the LangGraph agent, MCP and tests, without `platform` importing `features`.
- **Acceptance criteria:**
  - `_build_registry` is gone from the use case.
  - `build_tool_registry()` is public and unit-tested (it registers exactly `check_eligibility` and `log_claim`).
  - ADR-0003 says `tool_bindings.py` is generic and `server.py`, as a composition root, imports the feature catalogue.
  - `grep -r "ombuds.features" src/ombuds/platform` still returns nothing.
- **Depends on:** T-4 (the adapters move together with the error contract)

### T-6: Make the rules engine, not the LLM, the source of truth (F-01)
- **Files:** `features/claims_triage/tools/log_claim.py`, `application/decision.py`, `application/triage_use_case.py`, `platform/prompts/claims_triage/v4.txt` (new version, because the `log_claim` argument shape changes; bump `config.py` and `.env.example`), `tests/unit/features/claims_triage/{tools/test_log_claim.py, application/test_triage_use_case.py}`
- **Reason:** It restores the README's core claim before W2 makes `log_claim` reachable.
- **Acceptance criteria:**
  - `LogClaimArgs` = `claim_id` + `FlightDisruption`. `log_claim` calls `rules.evaluate()` and never accepts an `EligibilityResult` from the model.
  - A new function in `decision.py` checks a parsed `TriageDecision` against the latest non-error `check_eligibility` result. It flags a mismatch in `eligible`, in the amount, or in `reason_codes`, and it flags the case where no check was run. Any mismatch goes through the existing repair loop and counts against `MAX_REPAIR_ATTEMPTS`.
  - `compensation_amount_eur` is an `int`.
  - The tests cover:
    - a matching decision, which passes;
    - a mismatched amount, which is repaired;
    - a decision given without calling the tool, which is repaired;
    - repeated mismatch, which raises after the maximum number of attempts.
  - The existing test fixture `"EU261_ART7"` is replaced with real `Reason` codes.
- **Depends on:** T-5 (`log_claim` registration moves in T-5)

---

## 5. Optional Improvements

These are worth doing but don't block W2. Each is placed where it naturally fits.

| # | Improvement | When | Findings |
|---|---|---|---|
| O-1 | Golden-set smoke eval (8–10 claims, expected values from `rules.evaluate()`) and a baseline run before rewriting the loop | Before or at the very start of W2 task 1. Highest value | F-11 |
| O-2 | Stream/sync parity through one shared finalise-and-validate step, plus a `decision` SSE frame | Acceptance criterion of W2 "Rebuild tool-calling loop in LangGraph" | F-07 |
| O-3 | Construct the provider once in the composition root and inject it; tests use `dependency_overrides` | During the same W2 task (the graph needs the wiring) | F-13 |
| O-4 | Handle `stop_reason` (`max_tokens`, `refusal`), make `max_tokens` configurable with a realistic value, and confirm thinking-block behaviour with one live call | During the W2 loop rebuild | F-09, F-08 |
| O-5 | Typed triage errors with HTTP mapping, an SSE error frame, and non-convergence routed to escalation | W2 "escalation/retry loop" task | F-10 |
| O-6 | Decide how `AgentState` represents messages (the provider formats them, or neutral messages); fix the `FallbackProvider` docstring now | W2 design, first day | F-08 |
| O-7 | Hygiene: `openai` moved to a scripts group, `claim_text` `max_length`, AGENTS.md prompt line, stale script docstring, empty test placeholders, `pytest.raises` | Any time; about 30 minutes total | F-12, F-14 |

---

## 6. Proposed Pre-W2 Execution Plan

- [ ] **T-1:** Pass timeout and max-retries config to `AnthropicProvider`; remove the duplicate default model
- [ ] **T-2:** Add `ProviderUnavailableError` at the adapter boundary; `FallbackProvider` catches only that, with default `max_attempts=1`; add adapter tests
- [ ] **T-3:** Verify the `idempotency-key` header; remove it if unsupported; record `claim_id` idempotency as a W2 requirement
- [ ] **T-4:** Add `ToolExecutionError`; make `dispatch` return it as an error result; replace `NotImplementedError` in `log_claim`
- [ ] **T-5:** Add `build_tool_registry()` in `features/claims_triage/tools/`; amend ADR-0003 and AGENTS.md
- [ ] **T-6:** `log_claim` recomputes from facts; verify `TriageDecision` against the `check_eligibility` result through the repair loop; add prompt v4
- [ ] **O-1 (recommended):** Golden-set smoke eval plus a baseline run against the real API
- [ ] `make test` green; update `docs/progress/task_summaries.md` with a "Pre-W2 hardening" entry

Estimated effort: about 1–1.5 days. T-1 to T-5 are each under 2 h; T-6 is about half a day including the prompt bump.

---

## 7. Final Recommendation

**Ready for W2 after the required refactoring.**

The foundation is sound:

- the layering holds;
- the rules engine is exemplary;
- models are typed and frozen, and lint, mypy strict and the tests all pass;
- the deny-all gate is enforced in code rather than in the prompt.

Nothing needs restructuring. W2 can build on this layout as it is.

Six things should still be fixed first, because W2 builds directly on them:

- **F-01** is the one finding that hits the project's reason to exist. The system currently lets the model author the eligibility and the amount that a human approver and `log_claim` would act on. W2's first job is to make that approval path real, so this has to be fixed beforehand.
- **F-02, F-03 and F-04** are defects in the last W1 task (dead config, unclassified and multiplying retries, and an idempotency mechanism that most likely does nothing). The LangGraph rebuild will sit directly on this provider layer.
- **F-05 and F-06** are small contract and layering decisions that W2's MCP and approval tasks would otherwise make implicitly, and probably inconsistently.

Everything else (stream parity, DI, `stop_reason` handling, error mapping) is real but belongs *inside* the W2 tasks that rewrite that code. Fixing those items now would mean polishing code that is about to be replaced.
