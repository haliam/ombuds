# ombuds — Build Glossary

One entry per library, framework, or notable Python concept the first time it shows up in a task summary in [`task_summaries.md`](task_summaries.md). Append here whenever a summary's **Notable libraries** introduces something not already listed — don't duplicate an entry, just link back to the task that first used it.
Grouped by category; append new terms under the matching section.

## Python standard library

| Term | What it is |
|---|---|
| **`enum.StrEnum` (stdlib)** | An `Enum` whose members are also `str`, so they serialize as plain strings but are still a closed, typo-proof set at the type level — used for reason codes and action names.<br>↳ *First seen:* [EU261 rules engine](task_summaries.md#implement-eu261-rules-engine-verticalsairlinerulespy--unit-tests) |
| **`datetime.timedelta` (stdlib)** | Represents a duration as a first-class type instead of a bare int — prevents unit mistakes (hours vs. days) and supports direct comparison/arithmetic.<br>↳ *First seen:* [EU261 rules engine](task_summaries.md#implement-eu261-rules-engine-verticalsairlinerulespy--unit-tests) |
| **`dataclasses.dataclass` (stdlib)** | Lightweight, boilerplate-free way to define a plain data record (auto-generates `__init__`, `__repr__`, `__eq__`); unlike Pydantic it does no validation, so it's reserved for values that never cross a layer boundary.<br>↳ *First seen:* [Raw provider APIs](task_summaries.md#call-openai--anthropic-apis-directly-compare-outputs) |
| **`typing.Protocol` (stdlib)** | Structural typing: any object with matching method signatures satisfies the type, with no inheritance required — used for `LLMProvider` so a fake test provider or a future `OpenAIProvider` can stand in without subclassing.<br>↳ *First seen:* [FastAPI /triage](task_summaries.md#build-fastapi-triage-endpoint-raw-sdk-no-framework) |
| **`typing.TypeVar` (stdlib)** | Declares a placeholder type used to link an input and output type together generically — e.g. `parse_structured_output(text, schema: type[T]) -> T` says "whatever Pydantic model class you pass in, that's the type you get back," so callers of different schemas all get correctly-typed results from the one shared function instead of it returning a bare `BaseModel`.<br>↳ *First seen:* [Structured output](task_summaries.md#add-structured-output-validation-with-pydantic--retryrepair) |
| **`typing.TypedDict` (stdlib)** | Declares a plain `dict`'s expected keys and value types for type-checking purposes, without runtime validation (unlike Pydantic) or immutability — used for `AgentState` because LangGraph nodes return partial-`dict` state updates it merges by key, which needs a mutable mapping type, not a frozen model.<br>↳ *First seen:* [LangGraph loop](task_summaries.md#rebuild-tool-calling-loop-in-langgraph) |
| **Python generator** | A function containing `yield` runs lazily: each call to `next()` on it resumes the function until the next `yield`, producing one value at a time instead of building a whole list upfront. `stream_turn()`/`stream_triage()` are generators — the caller can start acting on the first event before the underlying provider call has even finished. `collections.abc.Iterator[T]` is the type-hint for "something you can pull values of type `T` out of one at a time."<br>↳ *First seen:* [Streaming + SSE](task_summaries.md#implement-streaming-sse--buffered-json-parsing) |
| **`threading.Lock` (stdlib)** | A mutex: `with lock:` ensures only one thread at a time runs the enclosed block, so concurrent reads/writes to a shared in-memory structure can't interleave into a corrupted state. Used by `ApprovalGate` (today the in-memory fake used in tests; the runtime store is Postgres) to guard its dict-backed request store, since FastAPI can serve requests from a thread pool (sync routes) concurrently.<br>↳ *First seen:* [Approval gate](task_summaries.md#replace-deny-all-stub-with-human-approval-gate-before-state-changing-tool-calls) |
| **`contextlib.ExitStack` (stdlib)** | Enters several context managers one after another and unwinds whichever ones were already entered if a later one fails; `pop_all()` hands the entered set to a new stack to close later. Used by `McpToolClient.__enter__` so a failed MCP connect still shuts down the portal thread it had already started.<br>↳ *First seen:* [Pre-W3 hardening](task_summaries.md#pre-w3-hardening) |

## Data validation (Pydantic)

| Term | What it is |
|---|---|
| **Pydantic** | Data-validation library: declares a model's shape and types once, validates on construction, and (with `frozen=True`) makes instances immutable after creation. Used for anything crossing a layer boundary (API payloads, tool args, domain results) per `docs/code-style.md`.<br>↳ *First seen:* [EU261 rules engine](task_summaries.md#implement-eu261-rules-engine-verticalsairlinerulespy--unit-tests) |
| **`pydantic.ValidationError`** | The exception Pydantic raises from `model_validate()`/`__init__` when data doesn't match a model's schema (wrong type, missing required field, failed constraint like `gt=0`). Its message lists every failing field, which is what makes it useful to feed straight back to a model as a repair prompt instead of just a generic "invalid" failure.<br>↳ *First seen:* [Structured output](task_summaries.md#add-structured-output-validation-with-pydantic--retryrepair) |
| **`pydantic.JsonValue`** | A type for any JSON-serialisable value (str, int, float, bool, None, and lists/dicts of those), validated recursively. Used for `ApprovalRequest.payload` so the platform-level gate can hold any feature's action payload while still guaranteeing it serialises to JSON, and can be deduped via a canonical `json.dumps(..., sort_keys=True)`.<br>↳ *First seen:* [Pre-W3 hardening](task_summaries.md#pre-w3-hardening) |

## Web & API (FastAPI, SSE)

| Term | What it is |
|---|---|
| **FastAPI** | ASGI web framework built on Pydantic + Starlette: request/response bodies are Pydantic models validated automatically, routes are grouped into `APIRouter`s and mounted onto an app. `TestClient` (backed by `httpx`) drives routes in tests without a running server.<br>↳ *First seen:* [FastAPI /triage](task_summaries.md#build-fastapi-triage-endpoint-raw-sdk-no-framework) |
| **FastAPI `Depends`** | FastAPI's dependency injection: a route parameter annotated `Depends(fn)` is filled by calling `fn` per request. Here `get_approval_store`/`get_registry` read what `create_app()` put on `app.state`, so routes never import a global and tests can pass their own.<br>↳ *First seen:* [Pre-W4 refactor](task_summaries.md#pre-w4-refactor-w3-review) |
| **FastAPI `lifespan`** | An async context manager passed to `FastAPI(lifespan=...)`: code before `yield` runs at startup, code after at shutdown. Used to open the Postgres pool and close it on shutdown; it only runs when the app is started (a `TestClient` used as `with TestClient(app)`).<br>↳ *First seen:* [Pre-W4 refactor](task_summaries.md#pre-w4-refactor-w3-review) |
| **FastAPI `StreamingResponse`** | A response type that takes a generator/iterator instead of a ready value, and sends each item it yields to the client as soon as it's produced rather than buffering the whole response first — how `/claims/triage/stream` turns `stream_triage()`'s generator into an SSE HTTP response.<br>↳ *First seen:* [Streaming + SSE](task_summaries.md#implement-streaming-sse--buffered-json-parsing) |
| **Server-Sent Events (SSE)** | A one-way, plain-HTTP streaming protocol: the server keeps the response open and pushes newline-delimited `data: <text>\n\n` frames whenever it has something new, and the client reads them as they arrive instead of polling. Simpler than WebSockets because it's unidirectional (server → client only) and needs no special protocol upgrade — just the `text/event-stream` content type. This is the wire format `POST /claims/triage/stream` uses to push each `StreamEvent` to the caller.<br>↳ *First seen:* [Streaming + SSE](task_summaries.md#implement-streaming-sse--buffered-json-parsing) |

## LLM provider SDKs

| Term | What it is |
|---|---|
| **`anthropic` / `openai` SDKs** | Official provider client libraries. DeepSeek has no dedicated SDK — it exposes an OpenAI-compatible API, so the `openai` client works against it with a different `base_url`.<br>↳ *First seen:* [Raw provider APIs](task_summaries.md#call-openai--anthropic-apis-directly-compare-outputs) |
| **`messages.stream()`** | The streaming counterpart to `messages.create()`: a context manager (`MessageStreamManager`) that, when iterated, yields raw low-level events (`content_block_start`/`_delta`/`_stop`, etc.) as the model generates its response, and exposes `get_final_message()` to retrieve the fully-assembled response afterward — used so `AnthropicProvider.stream_turn()`'s final `TurnDone` is built the same way `run_turn()` builds its `ProviderTurn`, regardless of how the stream was chunked.<br>↳ *First seen:* [Streaming + SSE](task_summaries.md#implement-streaming-sse--buffered-json-parsing) |

## LLM concepts

| Term | What it is |
|---|---|
| **Streaming (LLM response)** | Instead of waiting for a provider to finish generating the *entire* answer and returning it as one blob, the provider sends it incrementally — a token/text chunk at a time, plus partial tool-call arguments — over one still-open HTTP connection. Lets a client show text as it's generated instead of a multi-second blank wait. The trade-off: a caller now has to handle a value that arrives in pieces instead of one complete object, which is what `StreamEvent`/`JSONBuffer` exist to manage.<br>↳ *First seen:* [Streaming + SSE](task_summaries.md#implement-streaming-sse--buffered-json-parsing) |
| **Buffered/partial JSON parsing** | A streamed tool call's arguments don't arrive as one JSON value — they arrive as a sequence of text fragments (e.g. `{"disru`, then `ption": "cancel`, then `lation"}`) that are individually invalid JSON. "Buffering" means concatenating those fragments as they arrive and only attempting to `json.loads()` the result once the provider signals that call's input block is complete — `JSONBuffer` in `platform/ai/streaming.py` does exactly this, keyed per tool-call id so multiple in-flight calls don't get their fragments mixed together.<br>↳ *First seen:* [Streaming + SSE](task_summaries.md#implement-streaming-sse--buffered-json-parsing) |
| **Structured output (LLM concept)** | Constraining an LLM's reply to a fixed, machine-parseable shape (here: JSON matching a Pydantic schema) instead of accepting whatever free-text prose it produces, so downstream code can rely on specific fields being present and correctly typed rather than parsing prose or trusting the model's phrasing.<br>↳ *First seen:* [Structured output](task_summaries.md#add-structured-output-validation-with-pydantic--retryrepair) |
| **Retry/repair loop** | When a model's structured reply fails validation, instead of failing immediately the caller sends the validation error back to the model as the next turn ("your reply didn't validate: <error>, resend a corrected JSON object") and lets it try again, up to a fixed attempt cap. Distinct from a plain retry (which just resends the same request hoping for a different result): the model is given the *reason* it failed so it can actually fix it.<br>↳ *First seen:* [Structured output](task_summaries.md#add-structured-output-validation-with-pydantic--retryrepair) |

## Agent orchestration (LangGraph)

| Term | What it is |
|---|---|
| **LangGraph** | A graph-based orchestration layer on top of an LLM: you declare nodes (plain functions taking/returning a shared typed state) and edges (including conditional edges chosen by a routing function) instead of hand-writing the loop/branch logic yourself. `StateGraph(StateType)` builds the graph, `.compile()` produces a runnable `CompiledStateGraph`, and `.invoke(initial_state)` runs it to completion (here, `END` is reached once `finalize` sets `done=True`). Cycles are just edges that point back to an earlier node — that's how the tool-use loop (`call_model` ⇄ `dispatch_tools`, and `finalize` back to `call_model` for a repair) is expressed without a manual `for`/`while`.<br>↳ *First seen:* [LangGraph loop](task_summaries.md#rebuild-tool-calling-loop-in-langgraph) |
| **`get_stream_writer`** | Returns a callable a LangGraph node can use to emit arbitrary custom events while it runs; they reach the caller only when the graph is run with `app.stream(..., stream_mode="custom")` (combined here with `"values"` to also get the final state), and are a no-op under `app.invoke()`. Lets one graph serve both the blocking and the SSE endpoint: nodes emit tool-call/tool-result progress without knowing whether anyone is listening.<br>↳ *First seen:* [Pre-W3 hardening](task_summaries.md#pre-w3-hardening) |

## MCP (Model Context Protocol)

| Term | What it is |
|---|---|
| **MCP (Model Context Protocol)** | An open protocol for exposing tools/resources to an LLM client over a standard transport (stdio, SSE, HTTP), instead of a client and a tool provider needing a bespoke integration each time. A server declares its tools (`list_tools`) and executes them on request (`call_tool`); any MCP-speaking client — Claude Desktop, or this project's own `McpToolClient` — can then discover and call them without the server knowing anything about that specific client.<br>↳ *First seen:* [MCP server](task_summaries.md#stand-up-mcp-server-search_kb-check_eligibility-log_claim-issue_payment) |
| **`mcp` low-level `Server`** | The Python MCP SDK's low-level server: register handlers via decorators rather than deriving a tool's schema from a Python function's signature (as the SDK's higher-level `FastMCP` does). Used here so each tool's MCP `inputSchema` comes straight from its existing Pydantic `ToolDefinition.args_model` instead of a second, hand-written schema.<br>↳ *First seen:* [MCP server](task_summaries.md#stand-up-mcp-server-search_kb-check_eligibility-log_claim-issue_payment) |
| **`stdio_server`** | Wires an MCP `Server` to stdin/stdout as its transport, so it can be launched as a subprocess by an MCP client (Claude Desktop, `mcp.client.stdio.stdio_client`) rather than needing an HTTP listener.<br>↳ *First seen:* [MCP server](task_summaries.md#stand-up-mcp-server-search_kb-check_eligibility-log_claim-issue_payment) |
| **`stdio_client`** | The client-side counterpart to `mcp.server.stdio.stdio_server`: spawns a subprocess (via `StdioServerParameters(command=, args=)`) and connects to it over its stdin/stdout as an MCP transport, returning the `(read_stream, write_stream)` pair a `ClientSession` is built from. Used by `McpToolClient` to launch and talk to `python -m ombuds.platform.mcp.server` as a real separate process — the same way an external MCP client (Claude Desktop) would.<br>↳ *First seen:* [MCP client](task_summaries.md#connect-langgraph-agent-to-tools-over-mcp) |
| **MCP in-memory session** | A test helper that connects an MCP `Server` to a real `ClientSession` over in-memory streams (no subprocess, no sockets) — used so `test_tool_bindings.py` exercises the actual MCP request/response protocol, not just the handler functions called directly.<br>↳ *First seen:* [MCP server](task_summaries.md#stand-up-mcp-server-search_kb-check_eligibility-log_claim-issue_payment) |

## Approval & architecture concepts

| Term | What it is |
|---|---|
| **Executor** | The function registered for a guarded action (`log_claim`, `issue_payment`) that does the real write. It runs only after a human approves the request, never inline in the tool (ADR-0009).<br>↳ *First seen:* [Pre-W4 refactor](task_summaries.md#pre-w4-refactor-w3-review) |
| **Exactly-once execution** | An approved request runs its executor once: the store wins `PENDING → APPROVED`, runs the executor, then wins `APPROVED → EXECUTED`, so a second approve is refused (409) and writes nothing.<br>↳ *First seen:* [Pre-W4 refactor](task_summaries.md#pre-w4-refactor-w3-review) |
| **Compare-and-set** | A database update that only succeeds if the row is still in the expected state (`UPDATE ... WHERE status = ...`); two concurrent approvals can't both win.<br>↳ *First seen:* [Postgres + pgvector](task_summaries.md#set-up-postgres-relational--pgvectorchroma-embeddings) |
| **Composition root** | The one place that builds and connects the parts (pool, approval store, tool registry). Here `api_app.py` and the MCP server entrypoint; everything else receives its dependencies instead of importing a global.<br>↳ *First seen:* [Pre-W4 refactor](task_summaries.md#pre-w4-refactor-w3-review) |

## Async & concurrency

| Term | What it is |
|---|---|
| **`anyio`** | An async-runtime-agnostic concurrency library (runs on top of either `asyncio` or `trio`) that the `mcp` SDK is built on; `anyio.run()` is the SDK-consistent equivalent of `asyncio.run()` for `server.py`'s stdio entrypoint.<br>↳ *First seen:* [MCP server](task_summaries.md#stand-up-mcp-server-search_kb-check_eligibility-log_claim-issue_payment) |
| **`anyio` `BlockingPortal`** | A `BlockingPortal` runs an event loop on a background thread and lets synchronous code submit async work to it (`portal.call(coro_fn)`) and block for the result — used so `McpToolClient`'s synchronous `definitions()`/`dispatch_all()` methods can drive an async-only MCP `ClientSession` without LangGraph's synchronous nodes becoming async themselves. `wrap_async_context_manager()` additionally spawns one task that stays alive across the whole "entered" period and does both the `__aenter__` and (later) the matching `__aexit__` in that same task — needed because `anyio`'s cancel scopes (used inside `mcp`'s stdio transport) require whoever exits a scope to be the same task that entered it; calling `__aenter__`/`__aexit__` as two separate `portal.call()`s (two different spawned tasks) raises `RuntimeError: Attempted to exit a cancel scope that isn't the current task's current cancel scope`.<br>↳ *First seen:* [MCP client](task_summaries.md#connect-langgraph-agent-to-tools-over-mcp) |

## Testing

| Term | What it is |
|---|---|
| **`pytest.mark.parametrize`** | Runs one test function once per listed input, instead of copy-pasting near-identical test bodies — output shows each case as its own pass/fail.<br>↳ *First seen:* [Approval gate stub](task_summaries.md#stub-approval_gate-as-deny-all-before-any-state-changing-tool-is-registered) |
| **`pytest-asyncio`** | A pytest plugin that lets `async def test_...` functions run directly, by wrapping each in an event loop; `asyncio_mode = "auto"` in `pyproject.toml` applies this to every async test automatically, with no per-test `@pytest.mark.asyncio` needed.<br>↳ *First seen:* [MCP server](task_summaries.md#stand-up-mcp-server-search_kb-check_eligibility-log_claim-issue_payment) |

## Tooling & environment

| Term | What it is |
|---|---|
| **`uv`** | Fast Python package/project manager (Astral, same team as `ruff`) that replaces pip + virtualenv + pip-tools with one tool: resolves and installs dependencies, manages the project's virtual environment, and runs commands inside it via `uv run` (e.g. `uv run pytest`). Used for every `make` target in this repo.<br>↳ *First seen:* [FastAPI /triage](task_summaries.md#build-fastapi-triage-endpoint-raw-sdk-no-framework) |
| **`.venv`** | The project's virtual environment directory: an isolated Python install plus this project's dependencies, kept separate from system Python. `uv` creates and updates it automatically on first `uv run`, reading dependencies from `pyproject.toml` — no manual `activate` step needed.<br>↳ *First seen:* [FastAPI /triage](task_summaries.md#build-fastapi-triage-endpoint-raw-sdk-no-framework) |
| **`python-dotenv` (`load_dotenv`)** | Reads a `.env` file into `os.environ` at runtime — used for scripts/local dev; the app's own config path is separate.<br>↳ *First seen:* [Raw provider APIs](task_summaries.md#call-openai--anthropic-apis-directly-compare-outputs) |

## Documentation tooling

| Term | What it is |
|---|---|
| **archify** | A Claude Code skill that turns a typed JSON description into a standalone, interactive HTML diagram (architecture, sequence, workflow and more) and checks it in a real browser. Each diagram in `docs/diagrams/archify/` keeps its `.json` source, the generated `.html` and a `.png` screenshot.<br>↳ *First seen:* [Architecture diagram + README](task_summaries.md#write-architecture-diagram--readme-problem-design-trade-offs) |

## Data layer (Postgres)

| Term | What it is |
|---|---|
| **`psycopg` (psycopg3)** | The Python driver for Postgres (successor to `psycopg2`); runs SQL you write yourself, with parameter binding and `dict_row` row factories. `psycopg_pool.ConnectionPool` hands out connections, and each `with pool.connection()` block is one transaction.<br>↳ *First seen:* [Postgres + pgvector](task_summaries.md#set-up-postgres-relational--pgvectorchroma-embeddings) |
| **pgvector** | Postgres extension adding a `vector(N)` column type and distance operators (`<=>` cosine); lets embeddings live next to relational data (ADR-0010).<br>↳ *First seen:* [Postgres + pgvector](task_summaries.md#set-up-postgres-relational--pgvectorchroma-embeddings) |
| **HNSW index** | Approximate nearest-neighbour index (hierarchical navigable small world graph); trades a little recall for much faster vector search than a full scan. Created with `USING hnsw (embedding vector_cosine_ops)`.<br>↳ *First seen:* [Postgres + pgvector](task_summaries.md#set-up-postgres-relational--pgvectorchroma-embeddings) |
| **`INSERT ... ON CONFLICT`** | Postgres upsert: on a unique-constraint clash do nothing or update instead of erroring — how approval dedup avoids a read-then-write race.<br>↳ *First seen:* [Postgres + pgvector](task_summaries.md#set-up-postgres-relational--pgvectorchroma-embeddings) |

## RAG

| Term | What it is |
|---|---|
| **Embedding** | A fixed-length vector of numbers representing a text's meaning; texts with similar meaning get vectors pointing in similar directions. Here `text-embedding-3-small` produces 1536 numbers per text.<br>↳ *First seen:* [RAG pipeline](task_summaries.md#build-rag-pipeline--chunk--embed--store--retrieve--cite) |
| **Chunking** | Splitting documents into pieces small enough to embed and cite individually. Ours cuts at markdown headings so a chunk is one self-contained section.<br>↳ *First seen:* [RAG pipeline](task_summaries.md#build-rag-pipeline--chunk--embed--store--retrieve--cite) |
| **Cosine similarity** | How alike two vectors' directions are: 1.0 identical, 0.0 unrelated. The retriever's `score` is `1 - cosine_distance`, and hits below `min_score` are dropped.<br>↳ *First seen:* [RAG pipeline](task_summaries.md#build-rag-pipeline--chunk--embed--store--retrieve--cite) |
| **hit@k** | Fraction of questions whose correct chunk appears in the top k results. hit@5 of 0.96 means 25 of 26 questions found their section in the top 5.<br>↳ *First seen:* [Retrieval eval](task_summaries.md#build-small-eval-set-2030-qa-pairs-measure-retrieval-quality) |
| **MRR (mean reciprocal rank)** | Average of 1/rank of the first correct result (a miss counts 0). 1.0 means the right chunk is always first; it rewards ranking it higher, which hit@k doesn't.<br>↳ *First seen:* [Retrieval eval](task_summaries.md#build-small-eval-set-2030-qa-pairs-measure-retrieval-quality) |
| **Relevance floor** | The minimum cosine score for a hit to be returned (`DEFAULT_MIN_SCORE`). Too high drops right answers, too low returns weak matches; picked by sweeping it over the eval set.<br>↳ *First seen:* [Retrieval eval](task_summaries.md#build-small-eval-set-2030-qa-pairs-measure-retrieval-quality) |

## Guardrails

| Term | What it is |
|---|---|
| **PII (personal identifiable information)** | Data that identifies a person: email, phone, card and bank numbers, passport number. `pii_filter.redact` replaces it with placeholders like `[EMAIL]` before it leaves our process.<br>↳ *First seen:* [PII filtering](task_summaries.md#add-pii-filtering-on-inputsoutputs) |
| **Luhn checksum** | A check digit rule that valid card numbers satisfy; it lets the filter tell a card from any other 16-digit number.<br>↳ *First seen:* [PII filtering](task_summaries.md#add-pii-filtering-on-inputsoutputs) |
| **IBAN mod-97** | The checksum on international bank account numbers (move the first four characters to the end, read letters as numbers, remainder must be 1).<br>↳ *First seen:* [PII filtering](task_summaries.md#add-pii-filtering-on-inputsoutputs) |
| **Prompt injection** | Text in untrusted input that tries to give the model instructions ("ignore previous instructions"). `injection_detection.detect` flags it in the claim and the claim is escalated to a human instead of going to the model.<br>↳ *First seen:* [prompt-injection test cases](task_summaries.md#add-prompt-injection-test-cases) |
| **Unicode NFKC normalisation** | Folds look-alike characters (fullwidth `Ｉ`, ligatures) to their plain form, so obfuscated text matches the same patterns as the plain one. `unicodedata.normalize("NFKC", ...)` in the standard library.<br>↳ *First seen:* [prompt-injection test cases](task_summaries.md#add-prompt-injection-test-cases) |
| **`logging.Filter`** | A hook on a logger or handler that can edit or drop a log record before it is written. Attached to handlers here, since a logger's filters don't apply to records from its child loggers.<br>↳ *First seen:* [PII filtering](task_summaries.md#add-pii-filtering-on-inputsoutputs) |
| **Presidio** | Microsoft's open-source PII detector (regex recognisers plus spaCy NER, which catches names). The documented upgrade path if regex isn't enough.<br>↳ *First seen:* [PII filtering](task_summaries.md#add-pii-filtering-on-inputsoutputs) |
