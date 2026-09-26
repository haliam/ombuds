# ombuds — Build Task Summaries

One entry per finished task from `ombuds_build_tasks.md`. Recap for future-you, not documentation — that stays in docstrings/ADRs. Newest entries at the bottom.

Template — copy this block per finished task, filling in the fields (omit **Decisions/trade-offs** and **Follow-up** when there's nothing non-obvious to say):

```
### <task name from checklist>

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

**Goal:** Eyeball raw provider SDKs (text, latency, cost) on the same prompt before building any shared abstraction over them.
**Source:** W1 checklist, "Raw API Fundamentals"

**Files & responsibilities:**
- `scripts/compare_providers.py` — throwaway script, not part of the runtime provider layer (`platform/ai/providers/` is still stubbed). Calls Anthropic, OpenAI, and DeepSeek with the same EU261 prompt and prints text + latency + estimated cost side by side.

**Notable libraries:**
- `anthropic` / `openai` SDKs — call each provider directly, no shared client; DeepSeek reuses the `openai` SDK since it exposes an OpenAI-compatible endpoint (same client, different `base_url`).
- `python-dotenv` (`load_dotenv`) — loads API keys from `.env` for a local script run, not the app's own config path.
- `dataclasses` (`@dataclass(frozen=True)`) — `ProviderResult` is a plain immutable record; no cross-layer boundary here, so no Pydantic needed (per `docs/code-style.md`: Pydantic is for models crossing a layer boundary).

**Decisions/trade-offs:** Cost is an estimate hardcoded from published pricing at write-time, flagged in a comment to re-verify before trusting it — not fetched live.

---

### Stub `approval_gate` as deny-all before any state-changing tool is registered

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

## Glossary

One entry per library, framework, or notable Python concept the first time it shows up in a task above. Append here whenever a summary's **Notable libraries** introduces something not already listed — don't duplicate an entry, just link back to the task that first used it.

| Term | What it is | First seen in |
|---|---|---|
| Pydantic (`BaseModel`, `ConfigDict(frozen=True)`) | Data-validation library: declares a model's shape and types once, validates on construction, and (with `frozen=True`) makes instances immutable after creation. Used for anything crossing a layer boundary (API payloads, tool args, domain results) per `docs/code-style.md`. | Implement EU261 rules engine |
| `enum.StrEnum` (stdlib) | An `Enum` whose members are also `str`, so they serialize as plain strings but are still a closed, typo-proof set at the type level — used for reason codes and action names. | Implement EU261 rules engine |
| `datetime.timedelta` (stdlib) | Represents a duration as a first-class type instead of a bare int — prevents unit mistakes (hours vs. days) and supports direct comparison/arithmetic. | Implement EU261 rules engine |
| `dataclasses.dataclass` (stdlib) | Lightweight, boilerplate-free way to define a plain data record (auto-generates `__init__`, `__repr__`, `__eq__`); unlike Pydantic it does no validation, so it's reserved for values that never cross a layer boundary. | Call OpenAI & Anthropic APIs directly |
| `python-dotenv` (`load_dotenv`) | Reads a `.env` file into `os.environ` at runtime — used for scripts/local dev; the app's own config path is separate. | Call OpenAI & Anthropic APIs directly |
| `anthropic` / `openai` SDKs | Official provider client libraries. DeepSeek has no dedicated SDK — it exposes an OpenAI-compatible API, so the `openai` client works against it with a different `base_url`. | Call OpenAI & Anthropic APIs directly |
| pytest `@pytest.mark.parametrize` | Runs one test function once per listed input, instead of copy-pasting near-identical test bodies — output shows each case as its own pass/fail. | Stub `approval_gate` |
