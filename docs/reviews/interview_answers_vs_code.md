# Interview answers vs the code

Four interview answers were checked against the code on 2026-10-06. Each section lists where the answer says something the repo does not do (yet), or does differently, with the file to look at and a suggested fix. The visual explanations (one artifact per question) show only what the app does today; the gaps live here so they can be fixed in the repo.

Status values: **Gap** = the answer claims it, the code doesn't do it. **Differs** = the code does it another way. **Deliberate** = a recorded decision, not a defect.

Example claim used in the explanations: delay, 4 h arrival delay, 2,100 km, intra-EU, EU carrier. `rules.evaluate` returns `eligible=True, compensation_eur=400, reasons=("eligible",)`.

## Q1. Explain the tool/function-calling loop step by step

| Answer says | Repo does | Status | Where | Suggested fix |
| --- | --- | --- | --- | --- |
| One "authorize" step | Two layers: `scope_for_agent` (tool allowlist, `claim_id` pinned) then the approval gate | Differs | `features/claims_triage/tools/__init__.py`, `platform/guardrails/approval_gate.py` | None; describe both layers in the answer |
| Loop pauses when a step needs human approval | `log_claim` returns `pending` and the loop continues; execution happens once after approval | Differs | `tools/log_claim.py`, ADR-0009 | None; correct the answer |
| Stop on a token or cost budget | Only `MAX_TOOL_TURNS = 8`, `MAX_REPAIR_ATTEMPTS = 2` and unrecoverable stop reasons | Gap | `agent/graph.py` | Add a token budget to `AgentState`, escalate when exceeded |
| Detect repeated identical calls | Not implemented | Gap | `agent/graph.py` `dispatch_tools` | Hash `(name, arguments)` per run; escalate on N repeats |
| Execute independent calls concurrently | `dispatch_all` runs calls in order | Gap | `platform/ai/tool_loop.py` | Optional: run read-only calls concurrently, keep state-changing ones sequential |
| `tool_choice` to force or forbid tools | Provider never passes `tool_choice` | Gap | `platform/ai/providers/anthropic.py` | Only if a use for it appears (see Q2) |

## Q2. Why structured/tool-forced output over prompted JSON?

| Answer says | Repo does | Status | Where | Suggested fix |
| --- | --- | --- | --- | --- |
| Final output is forced via a tool or JSON-schema mode | Final verdict is prompted JSON plus parse, validate, repair | Deliberate | ADR-0005, `platform/prompts/claims_triage/v4.txt` | Revisit if evals show prompted-JSON failures |
| The classify step returns a Pydantic model (category, urgency, confidence) | `agent/nodes/classify.py` is a one-line stub; the structured result is `TriageDecision` | Gap | `agent/nodes/classify.py` | Build classify or drop it from the answer |
| Validation plus repair live in `structured_output.py` | Parsing and validation do; the repair loop is in `graph.py` `finalize`; content check is `verify_decision` | Differs | `platform/ai/schemas/structured_output.py`, `agent/graph.py`, `application/decision.py` | None; correct the answer |
| Low confidence routes to escalate | `TriageDecision` has no confidence field; escalation comes from turn cap, failed repairs, `max_tokens`, `refusal` | Gap | `application/decision.py` | Add a `confidence` field and an escalation threshold, or drop the claim |
| Enums over free text | `reason_codes` is `tuple[str, ...]`, compared to the rules engine's codes | Gap | `application/decision.py` | Use the `Reason` enum from `verticals/airline/rules.py` (needs a vertical-agnostic home, see import direction) |
| Evals make exact-match accuracy measurable | `evals/run_evals.py` is a placeholder | Gap | `evals/` | Build the runner and a first dataset |

## Q3. How do you reduce LLM cost and latency?

| Answer says | Repo does | Status | Where | Suggested fix |
| --- | --- | --- | --- | --- |
| Measure tokens, latency and cost per step; OpenTelemetry metrics | Provider never reads `response.usage`; `observability/metrics.py` and `tracing.py` are stubs | Gap | `platform/ai/providers/anthropic.py`, `platform/observability/` | Record `usage` per call first, then wire OTel (W4) |
| Prompt caching for the stable prefix | No `cache_control`; system prompt and tool list are identical on every call | Gap | `platform/ai/providers/anthropic.py` | Add a cache breakpoint after system and tools; check the prefix clears the minimum cacheable size |
| Smallest model per step, decided by evals | One loop on Sonnet; Haiku is only the availability fallback; `classify`, `retrieve`, `decide` nodes are stubs | Gap | `config.py`, `agent/nodes/` | Try Haiku for the whole loop behind the eval gate; `verify_decision` limits the risk |
| Shrink context: retrieve less, summarize history | `search_kb` and RAG are stubs; when built, the model picks `top_k` (default 5, max 20) | Gap | `tools/search_kb.py`, `rag/` | Cap `top_k` and snippet size server-side when retrieval lands |
| Cap output length | Fixed `MAX_TOKENS = 1024`; hitting it is an unrecoverable stop that escalates | Differs | `platform/ai/providers/anthropic.py`, `agent/nodes/escalate_retry.py` | Size per call, and consider retry with a higher cap before escalating |
| Parallelize independent tool calls | `dispatch_all` is sequential (little to gain: tools take microseconds) | Gap | `platform/ai/tool_loop.py` | Low priority |
| Stream so perceived latency drops | Streaming exists; model text is never forwarded (unverified verdict), only tool events | Differs | `agent/graph.py` | None; deliberate (W2 review F-07) |
| Batch API for offline work | Not used | Gap | `evals/` | Use when the eval runner exists |

## Q4. How do you handle a provider outage: retries/fallback?

| Answer says | Repo does | Status | Where | Suggested fix |
| --- | --- | --- | --- | --- |
| Circuit breaker so a dead provider fails fast | None; every call starts at the primary and pays its full retry budget (worst case about 90 s per model, 180 s with the fallback, per call) | Gap | `platform/ai/providers/fallback.py` | After N consecutive primary failures, skip it for a cool-down |
| Separate connect and read timeouts; idle timeout for streams | One 30 s timeout via `ANTHROPIC_TIMEOUT_SECONDS` | Gap | `config.py`, `providers/anthropic.py` | Pass an `httpx.Timeout` with separate values |
| Backoff with jitter in the fallback layer | `FallbackProvider` backoff is deterministic and off by default (`DEFAULT_MAX_ATTEMPTS = 1`); backoff and retry-after come from the SDK client | Differs | `providers/fallback.py` | None, or remove the unused backoff code |
| Fallback chain: smaller model, other provider, human queue | Sonnet then Haiku only; `openai.py` is a one-line stub | Gap | `providers/openai.py` | Implement when a second provider is needed (ADR-0006 "revisit") |
| Total outage: claim logged as pending for a human | `/triage` has no handler for `ProviderUnavailableError` (HTTP 500); the stream sends an error frame; nothing is queued | Gap | `features/claims_triage/api/routes.py`, `application/triage_use_case.py` | Return 503 or an escalated result; persist the claim as pending once Postgres lands (W3) |
| `issue_payment` idempotent on claim ID | Approval gate dedupes on `(action, payload)`; an approved request executes once; the agent is never offered `issue_payment` | Differs | `platform/guardrails/approval_gate.py`, ADR-0009 | None; correct the answer |
| Chaos-style test forcing the primary down | Unit tests with fake providers cover the paths; no integration test | Gap | `tests/unit/platform/ai/providers/test_fallback.py` | Add an integration test that fails the primary and checks the fallback's output passes `verify_decision` |
| `fallback.py` is where broad exception handling is allowed | Was true until W1 F-03; it now catches only `ProviderUnavailableError`, no bare `except Exception` remains in `src/` | Differs | `providers/fallback.py`, ADR-0006 | None; correct the answer |
