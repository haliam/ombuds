# Repo structure

Where everything lives and what each file is for. Imports go `features → platform → domain`, never the reverse; only the composition roots (`api_app.py`, `platform/mcp/server.py`) wire a feature into platform (ADR-0002). For the business framing see [architecture.md](../architecture.md); for the rules see [AGENTS.md](../../AGENTS.md).

Files marked *(placeholder)* are one-line stubs that reserve a place and do nothing yet.

```
ombuds/
├── src/ombuds/              the application
│   ├── domain/              shared business models and errors
│   ├── features/claims_triage/   the one feature: agent, RAG, tools, API, airline rules
│   └── platform/            feature-agnostic: AI, guardrails, MCP, infrastructure, observability, prompts
├── tests/                   unit (mirrors src/), integration (real Postgres/OPA), e2e
├── evals/                   quality measurements for the retriever and the agent
├── scripts/                 one-off developer scripts
├── docs/                    architecture, ADRs, diagrams, guides, progress, reports
├── .claude/skills/          project skills for Claude Code
├── .github/workflows/       CI
└── (root config)            Makefile, pyproject.toml, Docker, env template
```

## Root and tooling

| File | Responsibility |
|---|---|
| `Makefile` | Entry point for every dev task: run, test, lint, DB, OPA, ingest and evals (`make help`). |
| `pyproject.toml` | Package metadata, dependencies, and the ruff, mypy and pytest configuration. |
| `uv.lock` | Pinned dependency versions for reproducible `uv sync`. |
| `Dockerfile` | Builds the `ombuds` image used by the API and the migrate-ingest step. |
| `docker-compose.yml` | Defines the stack: Postgres + pgvector, one-shot migrate-ingest, OPA, and the API. |
| `.env.example` | Template for `.env`: keys, DB URL, API tokens, limits, tracing and live prompt version. |
| `.pre-commit-config.yaml` | Runs the lint checks and the gitleaks secret scan on every commit. |
| `.editorconfig` | Editor basics: indent, line endings, trailing whitespace. |
| `.dockerignore` | Keeps local state and secrets out of the Docker build context. |
| `.gitignore` | Keeps `.env`, virtualenvs and caches out of git. |
| `.vscode/settings.json` | Shared VS Code settings for the repo. |
| `.github/workflows/ci.yml` | CI on PRs and `main`: `make test`, policy tests, integration tests, gitleaks. |
| `README.md` | Project front page: what ombuds is and how to start. |
| `AGENTS.md` | Rules for coding agents: commands, layout, guardrails, prompt versioning. |
| `CLAUDE.md` | Imports `AGENTS.md` for Claude Code. |

## `src/ombuds/`

| File | Responsibility |
|---|---|
| `api_app.py` | Composition root: builds the FastAPI app and mounts the triage and approval routers. |
| `config.py` | Environment-backed settings and the versioned-prompt loader. |

### `domain/`

| File | Responsibility |
|---|---|
| `errors.py` | Domain-level error types. |
| `models/claim.py` | `Claim`, `EligibilityResult` and `ProposedAction`, the shared business models. |
| `models/enums.py` | `ClaimType` and `RiskLevel`. |

### `features/claims_triage/agent/`

| File | Responsibility |
|---|---|
| `graph.py` | LangGraph model/tool loop: model turn, dispatch tool calls, repeat until a final answer. |
| `state.py` | `AgentState`, the state threaded through every node of the loop. |
| `nodes/escalate_retry.py` | Routes a stuck or unverifiable run to human review instead of failing loud. |
| `memory/short_term.py` | Typed, rules-derived facts established during one triage run. |
| `memory/long_term.py` | The `LongTermMemoryStore` protocol: claimant facts that persist across runs. |
| `memory/postgres_long_term.py` | Postgres-backed long-term memory, adapting the claimant-facts repository. |

### `features/claims_triage/application/`

| File | Responsibility |
|---|---|
| `triage_use_case.py` | Orchestrates one end-to-end triage over the agent loop, with PII and injection checks at the seams. |
| `decision.py` | `TriageDecision` shape and `verify_decision`, which checks the model's verdict against the rules engine. |
| `runtime.py` | Builds the Postgres-backed approval store and tool registry for a composition root. |
| `executors.py` | What actually runs once a human approves a request (log the claim, record the payment). |

### `features/claims_triage/rag/`

| File | Responsibility |
|---|---|
| `chunking.py` | Splits a markdown policy document into heading-scoped chunks small enough to embed and cite. |
| `citation.py` | `Citation`: the provenance of a retrieved passage, so a decision can point to its policy source. |
| `ingest.py` | Turns the markdown documents in a directory into embedded chunks in the vector store; also the migrate-ingest entrypoint. |
| `retriever.py` | Embeds a query, searches the vector store, and returns cited passages above a relevance floor. |
| `embeddings.py` | *(placeholder)* Embedding lives in `platform/ai/embeddings.py`. |

### `features/claims_triage/tools/`

| File | Responsibility |
|---|---|
| `__init__.py` | The tool catalogue: builds the `ToolRegistry` with each tool wired to its handler and agent scope. |
| `search_kb.py` | Read-only: retrieves airline policy passages relevant to a query. |
| `check_eligibility.py` | Read-only: dispatches to the airline EU261 rules, never computes them itself. |
| `log_claim.py` | State-changing: only submits an approval request to log the claim. |
| `issue_payment.py` | State-changing: only submits an approval request for a payout. |

### `features/claims_triage/api/`

| File | Responsibility |
|---|---|
| `routes.py` | `POST /claims/triage` and the SSE variant `/claims/triage/stream`; thin, delegates to `application/`. |
| `schemas.py` | Request and response bodies for the triage routes. |

### `features/claims_triage/verticals/airline/`

| File | Responsibility |
|---|---|
| `rules.py` | The EU261 eligibility logic: distance tiers, delay thresholds, exemptions. The only place business rules live. |
| `evidence_schema.py` | The facts a claim must establish before the EU261 rules can be evaluated. |
| `kb_seed/eu261_summary.md` | Seed policy text: overview of EU261 rights and amounts. |
| `kb_seed/eu261_delays_cancellations.md` | Seed policy text: delay and cancellation rules. |
| `kb_seed/eu261_extraordinary_circumstances.md` | Seed policy text: the extraordinary-circumstances exemption. |

## `src/ombuds/platform/`

### `ai/`

| File | Responsibility |
|---|---|
| `providers/base.py` | Provider-agnostic contract for one LLM turn: conversation and tools in, assistant turn out. |
| `providers/anthropic.py` | Anthropic adapter using the raw SDK's tool-use turns. |
| `providers/openai.py` | *(placeholder)* Reserved for an OpenAI chat provider. |
| `providers/fallback.py` | Retries the primary model, then fails over to a secondary one. |
| `providers/budgeted.py` | Decorator that enforces a `UsageBudget` on every turn (ADR-0018). |
| `providers/traced.py` | Decorator that opens one OpenTelemetry span per model turn (ADR-0017). |
| `budget.py` | Shared ledger of tokens and estimated USD with a hard stop. |
| `usage.py` | Provider-agnostic token-usage value, so cost control is independent of any SDK. |
| `embeddings.py` | The `Embedder` contract plus the OpenAI adapter. |
| `streaming.py` | Provider-agnostic stream events and a buffer for incrementally arriving tool JSON. |
| `tool_loop.py` | Parses a provider's tool-use requests and dispatches each to its registered handler. |
| `schemas/structured_output.py` | Parses the model's final reply as JSON and validates it against a schema. |
| `schemas/tool_calls.py` | Provider-agnostic shape of a tool definition, a requested call, and its result. |

### `guardrails/`

| File | Responsibility |
|---|---|
| `approval_gate.py` | Human-approval gate: a state-changing action is submitted as a pending request, never run inline. |
| `executing_store.py` | Runs an approved request's executor exactly once. |
| `policy_engine.py` | OPA client that asks whether a guarded action may proceed; fails closed. |
| `policy_checked_store.py` | Approval store that asks the policy engine before accepting a submission. |
| `policies/payout_approval.rego` | Rego policy: payouts over the limit are denied at submit time. |
| `policies/payout_approval_test.rego` | Rego unit tests for the payout policy. |
| `pii_filter.py` | Replaces structured personal identifiers in free text with typed placeholders. |
| `guarded_dispatcher.py` | Tool dispatcher wrapper that redacts PII from every call's arguments. |
| `injection_detection.py` | Flags passenger text that tries to instruct the model instead of stating facts. |
| `audit_log.py` | Audit event vocabulary and the sink protocol every governance seam writes to. |
| `audited_dispatcher.py` | Tool dispatcher wrapper that records every call and outcome in the audit log. |
| `audited_store.py` | Approval store wrapper that records each approval transition in the audit log. |
| `api.py` | HTTP routes for the approval queue: list, get, approve, deny, execute. |
| `api_auth.py` | Static bearer-token auth, one credential per router, so the submitter cannot approve (ADR-0019). |

### `infrastructure/`

| File | Responsibility |
|---|---|
| `postgres.py` | Connection pool and the plain-SQL migration runner. |
| `repositories.py` | Postgres-backed approval store and claim, payment and claimant-facts repositories. |
| `vector_store.py` | Vector store protocol plus the pgvector implementation for KB chunk embeddings. |
| `audit_repository.py` | Postgres sink for the append-only `audit_log` table. |
| `migrations/0001_init.sql` | Initial schema: pgvector extension, approval requests, claims, long-term memory and KB chunks. |
| `migrations/0002_payments.sql` | Simulated payout records, one per logged claim. |
| `migrations/0003_audit_log.sql` | Append-only audit table with triggers that reject update and delete. |
| `migrations/0004_audit_refusals.sql` | Adds the scope-refusal and injection-escalation audit kinds. |

### `mcp/`

| File | Responsibility |
|---|---|
| `tool_bindings.py` | Wraps a `ToolRegistry` for MCP exposure without importing `features/`. |
| `server.py` | Composition root: standalone MCP server over stdio (`python -m ombuds.platform.mcp.server`). |
| `client.py` | Connects the agent loop to tools over a real MCP session instead of an in-process registry. |

### `observability/`

| File | Responsibility |
|---|---|
| `logging.py` | Log-handler filter that keeps PII out of every log line. |
| `tracing.py` | OpenTelemetry setup: spans for LLM turns, tool calls and policy checks. |
| `traced_dispatcher.py` | Tool dispatcher wrapper that opens one span per tool call. |
| `metrics.py` | *(placeholder)* Reserved for metrics. |

### `prompts/claims_triage/`

| File | Responsibility |
|---|---|
| `v1.txt`, `v2.txt`, `v3.txt` | Earlier triage prompt versions, kept as history. |
| `v4.txt` | The live triage prompt; bump the version rather than editing in place. |

## `evals/`

Quality measurements, not pass/fail tests.

| File | Responsibility |
|---|---|
| `run_evals.py` | Retrieval eval: scores the real retriever (hit@k, MRR) and sweeps the relevance floor (`make eval`). |
| `dataset.py` | Loads labelled retrieval questions and resolves their gold sections to chunk keys. |
| `retrieval_metrics.py` | Scores ranked search results against the chunks a question should find. |
| `run_agent_evals.py` | Agent eval: runs the real agent over labelled claims and reports misses (`make eval-agent`, costs money). |
| `agent_dataset.py` | Loads claims in the passenger's words with the outcome the agent should reach. |
| `datasets/airline_retrieval.jsonl` | Labelled questions for the retrieval eval. |
| `datasets/airline_claims.jsonl` | Labelled claims for the agent eval and the e2e run. |

## `scripts/`

| File | Responsibility |
|---|---|
| `compare_providers.py` | Compares raw Anthropic, OpenAI and DeepSeek outputs on the same prompt. |
| `ingest_docs.py` | *(placeholder)* Ingest is done by `rag/ingest.py`. |
| `seed_db.py` | *(placeholder)* Reserved for seeding the database. |

## `tests/`

| Path | Responsibility |
|---|---|
| `unit/` | One module per source module, mirroring `src/ombuds/` (plus `evals/`); no I/O. |
| `integration/` | Real Postgres, pgvector and OPA, and a real MCP round-trip; the LLM is mocked. |
| `e2e/` | *(placeholders)* The full-stack run is done by hand, see the e2e report. |
| `fakes.py` | Test doubles shared by unit and integration tests. |
| `api_auth.py` | Shared test credentials and the headers that present them. |
| `unit/conftest.py`, `integration/conftest.py` | Fixtures for each suite; integration skips (or fails under `CI`) when a service is unreachable. |
| `unit/platform/guardrails/{audit_fakes,store_fakes}.py`, `integration/policy_fakes.py` | Fakes for the governance tests. |

## `docs/`

| Path | Responsibility |
|---|---|
| `architecture.md` | Business framing and the component view of how the pieces fit. |
| `code-style.md` | The judgement-call rules: structure, types, where rules live, docstrings, errors, tests, diagrams. |
| `decisions/` | ADRs 0001–0019 (why things are shaped this way) and `0000-template.md` for new ones. |
| `diagrams/` | One folder per diagram with a versioned `README.md` page; plus the index, `_template.md` and the render scripts. |
| `guide/developer-guide.md` | How to run, debug and work on ombuds day to day. |
| `guide/db-queries.md` | Read-only SQL for inspecting the Postgres data. |
| `guide/demo-script.md` | A 10-minute live walkthrough of the system. |
| `guide/repo-structure.md` | This file. |
| `progress/tasks.md` | The task board; the source of truth for what is done. |
| `progress/task_summaries.md` | A short recap per finished task. |
| `progress/glossary.md` | Libraries and Python concepts, one entry each, first used in a task. |
| `reports/e2e-report-2026-10-26.md` | Result and recipe of the manual full-stack run with real claims. |

## `.claude/skills/`

| Path | Responsibility |
|---|---|
| `add-diagram/` | Adds or updates a diagram with the project's fixed folder, page, index row and ADR link. |
| `docs-cleanup/` | Audits the docs and writes a keep/update/trim/merge/delete plan. |
| `codebase-review/` | Pre-stage technical audit that writes one Markdown report. |
