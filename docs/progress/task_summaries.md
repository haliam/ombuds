# ombuds — Build Task Summaries

One entry per finished task from `tasks.md`. Recap for future-you, not documentation — that stays in docstrings and ADRs. Newest entries at the bottom. Keep each entry short: the goal, the files that matter, and any decision or correction that is not obvious from the code.

Template (omit **Decisions** and **Follow-up** when there is nothing non-obvious to say):

```
### <task name from checklist>

**Area:** <the section title in tasks.md>
**Goal:** <one sentence — the problem this task solves>
**Source:** <ADR # / review finding, if any>

**Files:**
- `file.py` — what it is responsible for, one line

**Notable libraries:** <only libraries doing something non-obvious here>
**Decisions:** <a judgment call and why>
**Follow-up:** <only if something is deliberately deferred>
```

---

## 1. Foundations: rules engine, raw LLM APIs, tool calling

### Implement EU261 rules engine (`verticals/airline/rules.py`) + unit tests

**Area:** Foundations: rules engine, raw LLM APIs, tool calling
**Goal:** Give the agent a deterministic, legally grounded eligibility and compensation calculator, so the LLM never invents EU261 numbers.
**Source:** ADR-0004; Regulation (EC) 261/2004; CJEU *Sturgeon* (C-402/07)

**Files:**
- `evidence_schema.py` — `FlightDisruption`/`Reroute`: the facts a claim must establish before rules can run. Facts only, no judgments.
- `rules.py` — `evaluate()`: scope (Art. 3) → extraordinary circumstances (Art. 5(3)) → delay threshold (Art. 7, *Sturgeon*) → cancellation notice (Art. 5(1)(c)) → tier by distance (Art. 7(1)) → reroute reduction (Art. 7(2)). The first exemption found wins.
- `claim.py` — `EligibilityResult`: the vertical-agnostic output (`eligible`, `compensation_eur`, machine-readable `reasons`).
- `test_rules.py` — boundary tests for every threshold, built from one baseline factory.

**Notable libraries:** Pydantic frozen models (evidence cannot be mutated), `StrEnum` reason codes, `timedelta` for every duration.
**Decisions:** a deliberately simplified subset of EU261. Voluntary denied boarding, missed connections across bookings, care rights and UK261 are out of scope, documented in the module docstring rather than half-implemented.

---

### Call OpenAI & Anthropic APIs directly, compare outputs

**Area:** Foundations: rules engine, raw LLM APIs, tool calling
**Goal:** Look at the raw provider SDKs (text, latency, cost) on the same prompt before building any shared abstraction.

**Files:**
- `compare_providers.py` — throwaway script, not part of the runtime. Calls Anthropic, OpenAI and DeepSeek with one EU261 prompt and prints text, latency and estimated cost side by side.

**Notable libraries:** `anthropic` and `openai` SDKs (DeepSeek reuses `openai` with a different `base_url`); `python-dotenv`; a frozen `dataclass` for `ProviderResult` (no layer boundary, so no Pydantic).
**Decisions:** cost is an estimate hardcoded from published pricing and flagged to re-verify, not fetched live.

---

### Stub `approval_gate` as deny-all before any state-changing tool is registered

**Area:** Foundations: rules engine, raw LLM APIs, tool calling
**Goal:** Guarantee `log_claim` and `issue_payment` can never execute before a real approval mechanism exists.
**Source:** ADR-0004

**Files:**
- `approval_gate.py` — `GuardedAction` and `check_approval()`, which denied every action unconditionally.
- `test_approval_gate.py` — parametrized, so a new guarded action is covered automatically.

**Follow-up:** replaced by the real human-approval gate in "Agent loop, MCP and human approval".

---

### Define tool schemas (`check_eligibility`, `log_claim`) + parse tool-use loop

**Area:** Foundations: rules engine, raw LLM APIs, tool calling
**Goal:** Give both tools a provider-agnostic schema and a dispatcher that turns a model turn's tool calls into results without an if/elif per tool.
**Source:** ADR-0004

**Files:**
- `tool_calls.py` — `ToolDefinition`, `ToolCall`, `ToolResult`: the provider-agnostic shapes, independent of any SDK.
- `tool_loop.py` — `ToolRegistry`: name → schema + handler. `dispatch_all()` validates arguments and turns an unknown tool or a validation failure into an error `ToolResult`, so one bad call cannot abort the rest of a turn.
- `check_eligibility.py` — read-only; its schema is `FlightDisruption` itself and it calls `rules.evaluate()`.
- `log_claim.py` — state-changing; checked the approval gate first.

**Decisions:** `check_eligibility` uses `FlightDisruption` as its schema instead of a wrapper model, since the tool takes exactly the rules engine's facts.

---

### Build FastAPI `/triage` endpoint (raw SDK, no framework)

**Area:** Foundations: rules engine, raw LLM APIs, tool calling
**Goal:** Wire the registry to a real provider turn and expose it over HTTP, with a raw `anthropic` tool-use loop (not LangGraph yet).

**Files:**
- `base.py`, `anthropic.py` — the `LLMProvider` Protocol (`run_turn`, `ProviderTurn`) and `AnthropicProvider`, so the use case is not coupled to Anthropic types.
- `config.py`, `v2.txt` — `load_prompt()` reads the versioned prompt; `CLAIMS_TRIAGE_PROMPT_VERSION` records which version is live.
- `triage_use_case.py` — `run_triage()`: loop `run_turn` → `dispatch_all` → feed results back until the model stops or `MAX_TOOL_TURNS` (8).
- `schemas.py`, `api/routes.py`, `api_app.py` — `POST /claims/triage` and the `create_app()` factory.
- `test_triage_use_case.py`, `test_routes.py` — a fake `LLMProvider` and `TestClient`; no real API calls.

**Notable libraries:** FastAPI (`APIRouter`, `TestClient`) and `httpx`.
**Decisions:** provider-agnosticism of the message history was deferred, since only Anthropic is wired. `run_triage()` takes `provider` as a keyword so tests can inject a fake without a mocking framework.

---

### Write unit tests for tool-calling parser + endpoint

**Area:** Foundations: rules engine, raw LLM APIs, tool calling
**Goal:** Close the edge-case gaps left by the `/triage` task: schemas, dispatch and the route had only happy-path coverage.

**Files:** `test_tool_calls.py` (new), plus added cases in `test_tool_loop.py` (a failing call does not abort the batch) and `test_routes.py` (missing `claim_text` is 422; a use-case exception propagates).

**Decisions:** the max-turns `RuntimeError` is asserted to propagate, documenting the behaviour at the time. Escalation replaced it later, in "Agent loop, MCP and human approval".

---

### Implement streaming (SSE) + buffered JSON parsing

**Area:** Foundations: rules engine, raw LLM APIs, tool calling
**Goal:** Stream the answer and tool calls as they happen, and assemble a tool call's arguments from the partial JSON fragments a streaming provider sends.
**Source:** ADR-0007

**Files:**
- `streaming.py` — the `StreamEvent` union (`TextDelta`, `ToolCallDelta`, `ToolResultEvent`, `TurnDone`) and `JSONBuffer`, which accumulates one call's `input_json_delta` fragments keyed by call id and parses them when the block closes.
- `anthropic.py` — `stream_turn()` over `client.messages.stream()`; the final `TurnDone` is built from `get_final_message()`, not the deltas, so it always matches `run_turn()`.
- `routes.py` — `POST /claims/triage/stream`, a `StreamingResponse` of `data: <json>\n\n` frames. The blocking endpoint is unchanged.

**Notable libraries:** `anthropic`'s `messages.stream()` and its raw content-block events.
**Decisions:** no test fakes the raw SDK stream events (too much surface); `LLMProvider.stream_turn()` is the tested boundary. A stream that drops mid-tool-call was left for the resilience task.

---

### Add structured output validation with Pydantic + retry/repair

**Area:** Foundations: rules engine, raw LLM APIs, tool calling
**Goal:** Force the model's final reply into a validated `TriageDecision`, and give it a chance to fix malformed JSON instead of failing the triage.
**Source:** ADR-0005

**Files:**
- `structured_output.py` — `parse_structured_output(text, schema)`: takes the outermost `{...}`, `json.loads`, then `model_validate`. Both failures raise one `StructuredOutputError` whose message is written to be sent back to the model.
- `decision.py`, `v3.txt` — `TriageDecision` (`eligible`, `compensation_amount_eur`, `reason_codes`, `explanation`) and the prompt's final-answer format. Plain-text replies, such as a question to the passenger, are still allowed.
- `triage_use_case.py` — a reply without `{` passes through (`decision=None`); one that fails validation triggers a repair turn, up to `MAX_REPAIR_ATTEMPTS` (2).

**Notable libraries:** `pydantic.ValidationError` (its text becomes the repair prompt), `typing.TypeVar`.
**Decisions:** prompted JSON plus client-side repair instead of native structured output (ADR-0005). `stream_triage()` was left unvalidated because validating there needs a feature-specific event inside `platform/`, which breaks the import direction. The prompt went straight to v3 because `evals/` was still a placeholder.
**Correction (before the agent-loop stage, 2026-09-27):** validation was shape-only, so a valid `TriageDecision` that disagreed with `check_eligibility`, or never called it, was accepted (first review, F-01). `verify_decision()` now checks it against the latest `check_eligibility` result through the same repair loop, `log_claim` takes flight facts rather than a model-authored `EligibilityResult`, and the prompt moved to v4.

---

### Add retries/backoff, timeouts, fallback model, idempotency

**Area:** Foundations: rules engine, raw LLM APIs, tool calling
**Goal:** Stop treating the Anthropic call as always-succeeds: timeouts, retries for transient failures, and a fallback model.
**Source:** ADR-0006

**Files:**
- `anthropic.py` — the client is built with `timeout` and `max_retries` (30 s / 2), so the SDK does the exponential backoff.
- `fallback.py` — `FallbackProvider`: retries the primary with its own backoff (`max_attempts` 3), then fails over to the fallback model. A stream fails over only if nothing has reached the caller yet; a mid-stream failure is re-raised rather than risking replayed output. `build_default_provider()` composes the two models from config.
- `test_fallback.py` — injectable `sleep`, so backoff does not slow the suite.

**Decisions:** two resilience layers (SDK retries, then model failover) instead of a retry library, and `FallbackProvider` is the one place allowed to catch bare `Exception` (ADR-0006).
**Correction (before the agent-loop stage, 2026-09-27):** the `idempotency-key` header added here is not supported by Anthropic's Messages API, so it did nothing and was removed. Idempotency belongs where a duplicate causes harm: the state-changing tools, keyed by `claim_id` (W1 review F-04).

---

## 2. Agent loop, MCP and human approval

### Rebuild tool-calling loop in LangGraph

**Area:** Agent loop, MCP and human approval
**Goal:** Replace the hand-rolled loop with an explicit `StateGraph`.
**Source:** ADR-0001

**Files:**
- `state.py` — `AgentState`, the `TypedDict` threaded through the nodes (messages, tool results, staged turn, counters, `answer`/`decision`, `done`).
- `graph.py` — `build_triage_graph(provider, registry, system)`: `call_model` → `dispatch_tools` (loops back) or `finalize` (verify the reply, or loop back with a repair message).
- `triage_use_case.py` — `run_triage()` invokes the compiled graph; the same `TriageResult` contract and bounds, and the existing tests passed with no edits.

**Notable libraries:** LangGraph (`StateGraph`, `END`).
**Decisions:** the nodes live in `graph.py` rather than `agent/nodes/*.py`, because the classify → retrieve → decide pipeline those stubs were for never existed. `stream_triage()` stayed on the old loop for the moment.
**Follow-up:** resolved later: `escalate_retry` was built, the other stubs were deleted, and `stream_triage` runs the same graph (see "Pre-RAG hardening of the agent path").

---

### Stand up MCP server (`search_kb`, `check_eligibility`, `log_claim`, `issue_payment`)

**Area:** Agent loop, MCP and human approval
**Goal:** Expose the tool catalogue over MCP so any MCP client can list and call it without knowing this feature exists.
**Source:** ADR-0003

**Files:**
- `search_kb.py`, `issue_payment.py` — new tools. `search_kb` raised until RAG existed; `issue_payment` mirrored `log_claim` behind the gate.
- `tool_bindings.py` — `build_mcp_server(registry)`: `list_tools`/`call_tool` read straight from the registry, so each tool has exactly one schema (`ToolDefinition.input_schema()`). A failed dispatch is re-raised so MCP returns `isError=True`.
- `server.py` — `python -m ombuds.platform.mcp.server`: the composition root, serving over stdio.
- `test_tool_bindings.py` — drives a real in-memory MCP client/server session, so the protocol layer is exercised, not just the handlers.

**Notable libraries:** `mcp` (low-level `Server`, `stdio_server`), `anyio`, `pytest-asyncio` with `asyncio_mode = "auto"`.
**Decisions:** pinned `mcp<2`, because v2 replaced the decorator API with constructor callbacks, a bigger change than this task needed. Also checked the server as a real subprocess over stdio, which the in-memory test cannot catch.

---

### Connect LangGraph agent to tools over MCP

**Area:** Agent loop, MCP and human approval
**Goal:** Let the graph dispatch tools over the real MCP transport, not just the in-process registry.

**Files:**
- `client.py` — `McpToolClient`: a synchronous context manager over an MCP `ClientSession` connected by stdio to the server subprocess. An `anyio` blocking portal bridges LangGraph's sync nodes to the async-only session; `wrap_async_context_manager` keeps enter and exit in one task, which avoids a cancel-scope error.
- `tool_loop.py` — the `ToolDispatcher` Protocol (`definitions()`, `dispatch_all()`); `ToolRegistry` and `McpToolClient` both satisfy it, so the graph does not care which it holds.
- `tool_calls.py` — `ToolDefinition.raw_schema`: an MCP-sourced tool carries the server's schema, with no dummy `args_model`.
- `triage_use_case.py` — `run_triage(use_mcp=False)`; `True` spawns the server.
- `test_client.py` — a real round trip against the actual subprocess.

**Notable libraries:** `anyio.from_thread.start_blocking_portal`.
**Decisions:** `use_mcp` defaults to false: the in-process registry has no startup cost and is what the tests exercise. One optional `raw_schema` field instead of a new spec type across the provider layer.

---

### Add short-term + long-term memory to agent state

**Area:** Agent loop, MCP and human approval
**Goal:** Carry facts forward within a run and across runs for the same claimant, instead of only the raw transcript.

**Files:**
- `short_term.py` — `ShortTermMemory`: frozen facts for one run; `remember()` returns a new instance.
- `long_term.py` — `LongTermMemory`, the `LongTermMemoryStore` Protocol and an in-memory store, a placeholder until Postgres.
- `graph.py`, `triage_use_case.py` — the context is added to the prompt; `run_triage` takes optional `claimant_id` and `long_term_store` and saves the final decision.

**Decisions:** the API is not wired to this: `TriageRequest` has no claimant identity, and inventing one for an in-memory dict would be wrong. Memory is prompt context only; eligibility still comes from `check_eligibility` and `verify_decision`.

---

### Add escalation/retry loop on low confidence

**Area:** Agent loop, MCP and human approval
**Goal:** Hand a run to a human instead of raising when it cannot reach a verified decision.

**Files:**
- `escalate_retry.py` — `UNRECOVERABLE_STOP_REASONS` (`max_tokens`, `refusal`) and the terminal `escalate` node.
- `graph.py`, `state.py` — non-convergence, repair exhaustion and an unrecoverable stop reason route to `escalate` instead of raising.
- `triage_use_case.py`, `schemas.py`, `routes.py` — `escalated` and `escalation_reason` on `TriageResult` and `TriageResponse`.

**Decisions:** there is no model-reported confidence in the schema, so "low confidence" means the failure modes the review before this stage listed (stop reason, non-convergence, repair exhaustion). Escalation is normal state, a 200 with a flag, not an exception: it is a business outcome the caller routes to a human.

---

### Replace deny-all stub with human-approval gate before state-changing tool calls

**Area:** Agent loop, MCP and human approval
**Goal:** Replace the deny-all stub with a minimal human-approval workflow, so a sign-off can actually happen.
**Source:** ADR-0008 (superseded by ADR-0009)

**Files:**
- `approval_gate.py` — `check_approval(action, context)` deduped on `(action, context)`: the first call creates a `PENDING` request and denies, a later call sees what a human resolved. `ApprovalGate` was in-memory and lock-guarded.
- `guardrails/api.py` — `GET /approvals`, `POST /approvals/{id}/approve|deny`.
- `log_claim.py`, `issue_payment.py` — pass the claim id as context.

**Notable libraries:** `threading.Lock`.
**Decisions:** in-memory store behind an interface, so Postgres was a swap, not a rewrite. The workflow is poll-based, because SSE is one-directional and a decision cannot be pushed into an in-flight run.
**Follow-up:** idempotency on `claim_id` at the persistence layer, and `approver` authentication, were deferred (done in "Durable approval path" and "Closing the governance holes").

---

### Pre-RAG hardening of the agent path

**Area:** Agent loop, MCP and human approval
**Goal:** Fix the governance-path gaps found in the review of the agent-loop stage before building persistence, RAG and guardrails on top.
**Source:** the agent-loop review (T-1 to T-6, O-7; git history); ADR-0009 (supersedes ADR-0008); ADR-0007 amendment

**Files:**
- `escalate_retry.py` — escalated runs return a fixed `ESCALATION_ANSWER`, never the model's last text.
- `short_term.py`, `long_term.py`, `graph.py` — memory holds only rules-derived fields; the system prompt is constant across a run.
- `0009-approval-request-is-the-pending-action.md` — the approval request *is* the pending action: tools only submit, an approved request executes exactly once, `claim_id` is server-issued, and the agent is not offered `issue_payment`.
- `tools/__init__.py` — `scope_for_agent(dispatcher, claim_id)` offers only `search_kb`/`check_eligibility`/`log_claim`, refuses other calls without dispatching them, and overwrites `claim_id` with the run's.
- `approval_gate.py`, `guardrails/api.py` — `submit(action, payload)` dedupes on the canonical payload; approve/deny only from `PENDING` (409 otherwise); a single-use `APPROVED → EXECUTED` transition.
- `log_claim.py`, `issue_payment.py` — both only submit; `issue_payment` takes facts and derives the amount from `evaluate()`.
- `graph.py`, `triage_use_case.py`, `routes.py` — `/claims/triage/stream` runs the same graph; frames are `tool_call`, `tool_result`, one `final` (or `error`). The manual loop is deleted.
- `client.py`, `schemas.py` — no portal-thread leak on a failed connect; `claim_text` capped at 10,000 chars.

**Notable libraries:** `langgraph.config.get_stream_writer`, `pydantic.JsonValue`, `contextlib.ExitStack`.
**Decisions:** `claim_id` stays in the tool schemas (MCP clients need it) and is overwritten for the agent, so a model that guesses an id cannot loop on errors. The stream dropped `text_delta` frames because the final reply is an unverified verdict until `finalize` checks it.

---

## 3. Data layer, RAG and guardrails

### Set up Postgres (relational) + pgvector/Chroma (embeddings)

**Area:** Data layer, RAG and guardrails
**Goal:** A durable, cross-process data layer: Postgres for relational state and pgvector for KB embeddings.
**Source:** ADR-0009, ADR-0010 (pgvector over Chroma, psycopg3 over an ORM)

**Files:**
- `docker-compose.yml`, `config.py` — the `db` service (`pgvector/pgvector:pg16`, host port 5433) and `DATABASE_URL`.
- `postgres.py`, `0001_init.sql` — pool and a numbered-SQL migration runner (advisory-locked); `approval_requests` (UNIQUE `(action, payload_key)`), `claims`, `long_term_memory`, `kb_chunks` with an HNSW cosine index.
- `repositories.py` — `PostgresApprovalStore` (upsert dedup, compare-and-set transitions) and the claimant-facts repository.
- `vector_store.py` — `VectorStore` Protocol and `PgVectorStore`.
- `tests/integration/` — session pool, per-test truncate, and concurrent-claim race tests.

**Notable libraries:** `psycopg`/`psycopg_pool`, pgvector, HNSW, `INSERT ... ON CONFLICT`.
**Decisions:** vectors go in as text literals (`%s::vector`), so neither the `pgvector` package nor numpy is needed.

---

### Build RAG pipeline — chunk → embed → store → retrieve → cite

**Area:** Data layer, RAG and guardrails
**Goal:** Let the agent look up airline policy through `search_kb` and get passages it can cite.
**Source:** ADR-0010, ADR-0011

**Files:**
- `platform/ai/embeddings.py` — `Embedder` Protocol and `OpenAIEmbedder`.
- `rag/chunking.py`, `kb_seed/*.md`, `rag/ingest.py` — heading-aware chunking of three EU261 documents; `make ingest` replaces a source's chunks in one transaction.
- `rag/retriever.py`, `rag/citation.py` — `Retriever` with a relevance floor and a `Citation` model.
- `tools/search_kb.py` — takes an injected retriever; hits carry `chunk_index` and `score`.

**Notable libraries:** the `openai` SDK (embeddings endpoint).
**Decisions:** the retriever is built lazily, so the registry needs no database or API key. The unused `classify`/`retrieve`/`decide` node stubs were deleted.

---

### Build small eval set (20–30 Q/A pairs), measure retrieval quality

**Area:** Data layer, RAG and guardrails
**Goal:** Measure how well `search_kb` finds the right section, and pick the relevance floor from data.
**Source:** ADR-0012

**Files:**
- `evals/datasets/airline_retrieval.jsonl` — 30 questions: 26 answerable (gold = file + heading) and 4 off-topic.
- `evals/retrieval_metrics.py`, `evals/run_evals.py` — hit@k, MRR and off-topic rejection; `make eval` sweeps the floor.
- `rag/retriever.py` — `DEFAULT_MIN_SCORE` 0.2 → 0.35.

**Decisions:** gold is labelled by heading, not chunk index, so re-chunking does not invalidate it. Result: hit@5 0.96, MRR 0.84. The floor mostly cannot separate off-topic from answerable because the scores overlap (0.384 vs 0.389).
**Follow-up:** `scope-2` misses at every floor; grow the off-topic set.

---

### Add PII filtering on inputs/outputs

**Area:** Data layer, RAG and guardrails
**Goal:** Keep personal identifiers out of the LLM and embedding APIs, the response, the logs and the approval records.
**Source:** ADR-0013

**Files:**
- `pii_filter.py` — `redact`/`redact_value`: regex detection with Luhn and mod-97 checks, typed placeholders, per-kind counts.
- `guarded_dispatcher.py` — redacts the arguments of every tool call for any `ToolDispatcher`.
- `triage_use_case.py` — redacts `claim_text` on the way in; the answer, explanation, escalation reason and streamed frames on the way out.
- `approval_gate.py`, `mcp/server.py`, `logging.py` — redacted approver note; the MCP server guards external clients; `PiiRedactingFilter` on log handlers.

**Notable libraries:** stdlib `re` and `logging` only.
**Decisions:** regex and checksums instead of Presidio, so names and addresses are not covered. Redaction is one-way with no off switch.

---

### Add prompt-injection test cases

**Area:** Data layer, RAG and guardrails
**Goal:** Stop passenger text that tries to instruct the model from reaching it, and prove the structural guardrails hold when detection misses.
**Source:** ADR-0014

**Files:**
- `injection_detection.py` — `detect()`: normalise, regex per kind, base64 decode and rescan; counts only.
- `triage_use_case.py` — a flagged claim is escalated before any model call, tool dispatch or memory write.
- tests — attacks per kind, obfuscation, a false-positive corpus including the KB seed, and a paraphrase that evades detection still cannot trigger `issue_payment`.

**Notable libraries:** stdlib `unicodedata` and `base64`.
**Decisions:** heuristics, not an LLM classifier; escalate, not reject. The structural limits (tool scope, server-issued `claim_id`, approval gate) are the real defence.
**Follow-up:** paraphrase and non-EN/DE/FR/ES attacks are missed. The agent-level injection case was later added to the eval set.

---

### Write integration test for `/triage` end-to-end

**Area:** Data layer, RAG and guardrails
**Goal:** Prove HTTP → `run_triage` → LangGraph → scoped, guarded tools → Postgres works as one path.

**Files:**
- `tests/integration/api/test_triage_endpoint.py` — the real `create_app()` through `TestClient`: a verified decision after a real pgvector `search_kb`, `log_claim` parked under the server-issued `claim_id`, a clarifying question, injection and contradiction escalations, SSE frames matching the JSON endpoint, 422 on empty input.
- `tests/fakes.py` — `ScriptedProvider`, a replay-only `LLMProvider`.

**Decisions:** only the LLM and the embedder are faked. Checked the test can fail by breaking `scope_for_agent`'s `claim_id` binding.

---

### Write Docker Compose for full stack, verify `docker compose up`

**Area:** Data layer, RAG and guardrails
**Goal:** One command brings up the database, the schema and KB, and the API.

**Files:**
- `Dockerfile`, `.dockerignore` — `python:3.11-slim` with `uv sync --frozen --no-dev`, non-root, uvicorn on :8000.
- `docker-compose.yml`, `Makefile` — a one-shot `migrate-ingest` and the `api` service (waits via `service_completed_successfully`; healthcheck on `/openapi.json`); `make up` and `make down`.
- `logging.py` — fixed a bug the stack exposed: the PII filter set `record.args = None`, which broke uvicorn's access log.

**Decisions:** the API does not migrate on startup; the one-shot service owns schema and KB. No separate MCP service: the stdio server is a subprocess of the API container (ADR-0003).
**Verified:** clean `down -v` → `make up` → real triage with `log_claim` parked; a second `make up` is idempotent.

---

## 3b. Durable approval path (composition-root refactor)

### Durable approval path (composition-root refactor)

**Area:** Durable approval path (composition-root refactor)
**Goal:** Finish the approval path the data-layer stage left open, so the tracing, audit and policy attach to a durable, executing path.
**Source:** the data-layer review (P-1 to P-4; git history); ADR-0009 addendum

**Files:**
- `approval_gate.py`, `api_app.py` — the module-level `_GATE` is gone; `create_app()` is the composition root (a lifespan opens the Postgres pool; routes use `Depends`).
- `application/runtime.py`, `mcp/server.py` — `build_runtime(pool)` builds the Postgres approval store and the registry once; the API and the MCP subprocess share approvals.
- `executing_store.py` — `ExecutingApprovalStore.approve` wins `PENDING → APPROVED`, runs the executor, then wins `APPROVED → EXECUTED`; `execute_approved` is the recovery path.
- `executors.py`, `0002_payments.sql` — `log_claim` writes `claims`; `issue_payment` needs a logged claim with a matching amount and writes a simulated `payments` row. Both are idempotent on `claim_id`.
- `triage_use_case.py` — `_prepare_run` is the one preamble for `run_triage` and `stream_triage`.

**Notable libraries:** FastAPI `lifespan` and `Depends`.
**Decisions:** idempotent write, then claim, instead of one transaction (ADR-0009 addendum): a simpler store protocol, at the cost that a failed executor leaves the request `APPROVED` until `execute_approved` runs (made reachable in "Closing the governance holes").
**Verified:** a real triage parked a request, it survived an API restart, approving it wrote exactly one `claims` row, and a second approve returned 409.

---

## 4. Observability and governance

### Write architecture diagram + README (problem, design, trade-offs)

**Area:** Observability and governance
**Goal:** Give the project a readable front door: diagrams traced from the code, and a README that states the problem, design and trade-offs without claiming anything unbuilt.

**Files:**
- `docs/diagrams/architecture/`, `claim-sequence/` — a component view and a sequence view (archify; the sequence was first drawn as `triage-approval-flow`, later merged into `claim-sequence`), pinned to a commit. The development-overview board was added afterwards (since redrawn as one board, v2.0).
- `docs/architecture.md`, `README.md` — embeds the diagrams and a component table; the README is Problem, Design, Trade-offs (linking each ADR) and Known limitations.

**Notable libraries:** archify (Claude Code skill).
**Decisions:** the generated HTML was first left out under a 500 KB hook limit, then committed after the limit moved to 1000 KB, and later dropped as a build output (only `.json` and `.png` are kept). OTel, Rego and audit were listed as planned rather than drawn.

---

### Write one OPA/Rego policy (block auto-payout above €X)

**Area:** Observability and governance
**Goal:** A real policy-as-code check in front of state-changing actions: a payout above the ceiling is refused before any approval request exists.
**Source:** ADR-0015

**Files:**
- `policies/payout_approval.rego` (+ `_test.rego`) — denies `issue_payment` above `input.limits.max_payout_eur` or with a missing or non-numeric amount; exposes `decision` = `{allow, reasons, policy_version}`.
- `policy_engine.py` — `PolicyEngine` Protocol and `OpaHttpPolicyEngine` (stdlib HTTP, fails closed with `policy_unavailable`).
- `policy_checked_store.py` — an `ApprovalStore` decorator that evaluates on `submit` and raises `PolicyDeniedError`.
- `runtime.py`, `docker-compose.yml`, `Makefile` — the engine and limit are injected by the roots; an `opa` service; `opa-up` and `test-policy`.

**Notable libraries:** OPA / Rego; `urllib.request`.
**Decisions:** an OPA server sidecar, since no embedded engine is installable in Python. The limit is passed in as input, so the Rego holds no number. Denial at submit means nothing over the limit reaches the human queue.
**Follow-up:** the policy runs at submit only, not again at approve.

---

### Build audit trail — log every tool call + decision

**Area:** Observability and governance
**Goal:** A durable, tamper-resistant record of every tool call, policy verdict and approval transition for a claim.
**Source:** ADR-0016

**Files:**
- `0003_audit_log.sql` — the `audit_log` table; triggers reject UPDATE/DELETE/TRUNCATE; nullable `trace_id`.
- `audit_log.py`, `audit_repository.py` — `AuditEvent`, `AuditKind`, the `AuditLog` Protocol and `PostgresAuditLog`.
- `audited_dispatcher.py`, `audited_store.py`, `policy_checked_store.py` — record tool calls (redacted arguments, truncated result), approval transitions (ids and approver only) and policy verdicts.
- `runtime.py` — wires all three.

**Decisions:** decorators at the existing seams rather than calls inside tools; immutability enforced by database triggers; the audit insert is a separate transaction from the state change (a documented gap); it fails closed on write errors.

---

### Add OpenTelemetry tracing (span per LLM/tool call)

**Area:** Observability and governance
**Goal:** One claim is one trace: a span per LLM turn, tool call and policy check, with no claim content in any attribute, and each audit row linked to its trace.
**Source:** ADR-0017

**Files:**
- `tracing.py` — `configure_tracing` (`none` | `console` | `otlp`), `start_span`, `trace_stream` for SSE; a no-op by default.
- `traced.py`, `traced_dispatcher.py` — `TracedProvider` wraps each concrete adapter (a failover shows as two sibling spans); `TracedDispatcher` sits outside `AuditedDispatcher`.
- `policy_checked_store.py`, `triage_use_case.py`, `audit_repository.py` — `policy.check`, a `triage.run` root span, and `trace_id` stamped on every audit row.

**Notable libraries:** `opentelemetry-api`/`-sdk`/OTLP exporter.
**Decisions:** spans carry ids, model, stop reason, counts and verdicts only; an exception sets the status to its type, not its message. `trace_stream` makes the span current only while the source produces an event, because FastAPI resumes sync generators on different threads.
**Follow-up:** the MCP subprocess starts its own traces (no propagation).

---

## 5. Closing the governance holes

### Make approved-but-failed requests recoverable

**Area:** Closing the governance holes
**Goal:** Give the ADR-0009 "failed executor is recoverable" guarantee a reachable code path.
**Source:** ADR-0009 addendum

**Files:**
- `approval_gate.py`, `policy_checked_store.py` — `ExecutableApprovalStore(ApprovalStore)` adds `execute_approved`; the decorators delegate it; `ApprovalGate` is unchanged.
- `guardrails/api.py` — `approve` maps `ToolExecutionError` to a 502 body `{detail, request_id, status: approved}`; `POST /approvals/{id}/execute` retries (409 for a non-approved request). Other exceptions are 500s, logged with the request id.

**Decisions:** 502 rather than 409, so a state conflict stays distinguishable from a failed downstream effect. No automatic retry.
**Verified:** an integration test over Postgres: a payment for an unlogged claim returns 502, log the claim, `/execute` writes one `payments` row.

---

## 6. Automated guards, evals and cleanup

### Complete the audit trail

**Area:** Automated guards, evals and cleanup
**Goal:** Record the two refusals the audit could not see, give approval decisions a trace id, and stop a docstring overpromising.
**Source:** the first governance review (F-06; git history); ADR-0016 (amended)

**Files:**
- `0004_audit_refusals.sql`, `audit_log.py` — `tool_refused` and `injection_escalation` kinds.
- `tools/__init__.py` — `scope_for_agent(..., audit)` records a call outside the agent's set (redacted arguments, capped name).
- `triage_use_case.py`, `runtime.py`, `routes.py` — an `audit` parameter; the injection escalation is recorded inside a `triage.injection_escalation` span.
- `guardrails/api.py` — `approvals.approve|deny|execute` spans.
- `audit_repository.py` — the docstring no longer claims an action cannot proceed unaudited.

**Decisions:** the sink is passed in rather than wrapped around the scope, because the refusal happens in feature code outside the audited dispatcher. `audit` is optional, so unit tests need no database.

---

Library, framework and concept entries live in [`glossary.md`](glossary.md) — append there, not here, whenever a summary's **Notable libraries** introduces something not already listed. The other tasks in the last two sections (network lockdown, bearer-token auth, DB default, CI and gitleaks, agent eval, spend cap) have no entry here: their record is in [ADR-0018](../decisions/0018-process-wide-llm-spend-cap-in-a-provider-decorator.md), [ADR-0019](../decisions/0019-static-bearer-tokens-per-router.md) and `tasks.md`.
