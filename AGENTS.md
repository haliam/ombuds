# AGENTS.md — ombuds

## Project overview
`ombuds` is a governed, observable agentic claims-triage system. The first (and currently only) vertical is airline EU261 refund/compensation claims. Python + FastAPI + LangGraph agent, RAG over airline policy docs, tools exposed both directly and via MCP, guardrails (PII filtering, injection detection, approval gates, OPA/Rego policy) in front of any state-changing action.

Built in weekly stages as an interview-prep capstone for an AI/Agentic Engineer role; `docs/progress/tasks.md` is the task board and the source of truth for what is done. See `docs/architecture.md` for the business framing and `docs/decisions/` for why things are shaped the way they are — check there before re-litigating a decision that's already been made.

## Stack
Python ≥3.11 · FastAPI · LangGraph · MCP · PostgreSQL + pgvector (ADR-0010) · OpenTelemetry · OPA/Rego · Docker Compose · pytest

## Commands
Keep this section accurate or delete a stale line — a wrong command here is worse than no command. `make help` is the live list of targets; the full run/debug guide is `docs/guide/developer-guide.md`. This section only holds what an agent needs to decide **what to run, when, and what it costs**. Verified against the Makefile on 2026-10-26.

### Before you commit
| Command | When | What it does |
|---|---|---|
| `make test` | every commit | `make lint` (ruff check + ruff format --check + mypy strict), then `uv run pytest tests/unit`. `make format` auto-fixes. Config in `pyproject.toml`; `uv` creates `.venv` on first run |
| `make test-policy` | after touching `policies/*.rego` or the payout limit | `opa check` + Rego unit tests (`*_test.rego`) in the OPA container |
| `make test-integration` | after touching stores, repositories, migrations, RAG or the API | starts Postgres (+ pgvector) and OPA, runs `tests/integration`; the LLM is mocked |
| `make eval-agent` | **before a new prompt version goes live** | runs the real agent over `evals/datasets/airline_claims.jsonl` and prints outcome/verdict accuracy plus the misses. **Costs money**; report only, never fails |

CI (`.github/workflows/ci.yml`, on PRs and `main`) runs `make test`, `make test-policy`, `tests/integration` (under `CI` an unreachable service fails the suite instead of skipping) and a gitleaks scan. Pre-commit (`uv run pre-commit install`, once) runs the same lint checks plus gitleaks on every commit. GitHub push protection is on.

### Run the app
| Command | What it does |
|---|---|
| `make run` | Postgres, then the API on `:8000` with reload, outside Docker. Start OPA first (`make opa-up`): state-changing tools fail closed without it |
| `make up` / `make down` | whole stack in Docker: db, one-shot `migrate-ingest` (migrations + KB ingest), OPA, API on `localhost:8000`. `down` keeps the Postgres volume |
| `make ingest` | chunk + embed `verticals/airline/kb_seed/*.md` into pgvector; safe to re-run |
| `make eval` | `make ingest`, then retrieval hit@k/MRR per relevance floor over `evals/datasets/airline_retrieval.jsonl`; report only |
| `uv run python -m ombuds.platform.mcp.server` | the standalone MCP server over stdio, with the same Postgres-backed approvals as the API; needs the db up |

`make db-up`, `db-down`, `opa-up`, `logs` and `ps` do what their names say. **`make db-reset` is destructive** (deletes the Postgres volume, so every claim and approval): never run it unless asked.

### Environment (`.env`, never committed; template is `.env.example`)
- **Keys:** `ANTHROPIC_API_KEY` for the agent; `OPENAI_API_KEY` for embeddings (ingest, `make up`, both evals).
- **Database:** `POSTGRES_PASSWORD` and `DATABASE_URL` have no default password. `OMBUDS_ALLOW_DEV_DEFAULTS=1` opts in to a throwaway dev URL.
- **API auth (ADR-0019):** `OMBUDS_TRIAGE_TOKEN` for `/claims/*`, a different `OMBUDS_APPROVER_TOKEN` for `/approvals*`, and `OMBUDS_APPROVER` (the name recorded on decisions). If any is empty the protected endpoints answer 503.
- **Limits:** `PAYOUT_LIMIT_EUR` (default 400) is the payout ceiling; `LLM_BUDGET_MAX_USD` / `LLM_BUDGET_MAX_TOKENS` cap LLM spend per process (ADR-0018).
- **Tracing:** `OTEL_TRACES_EXPORTER=console` (or `otlp` + `OTEL_EXPORTER_OTLP_ENDPOINT`) emits spans for LLM turns, tool calls and policy checks (ADR-0017); default `none`.
- **Prompt:** `CLAIMS_TRIAGE_PROMPT_VERSION` records the live version (see "Prompt versioning").

## Layout (feature-sliced — see ADR-0002)
`src/ombuds/` has three areas. Import direction is `features → platform → domain`; never the reverse. The only modules allowed to wire a feature into platform are the composition roots: `api_app.py` and the MCP server entrypoint.

- `domain/` — shared business models (`models/claim.py`, `enums.py`) and `errors.py`. No LLM, agent, HTTP or DB concerns.
- `features/claims_triage/` — everything specific to the one feature:
  - `verticals/airline/` — `rules.py` (EU261 tiers, exemptions), `evidence_schema.py`, `kb_seed/`. Only `airline/` exists; no vertical registry/ABC until a second one does.
  - `application/` — `triage_use_case.py` (orchestrates a triage), `decision.py` (`verify_decision`: checks the model's verdict against the rules engine), `runtime.py` (builds the Postgres-backed approval store + tool registry for a composition root), `executors.py` (what runs once a request is approved).
  - `agent/` — LangGraph `graph.py` (the model/tool loop only: no checkpointer, no approval node; ADR-0001), `state.py`, `nodes/` (`escalate_retry` only — classify/retrieve/decide happen inside the model's tool loop and `finalize`), `memory/`.
  - `rag/` — chunking, embeddings, ingest, retrieval, citation.
  - `tools/` — `search_kb`, `check_eligibility`, `log_claim`, `issue_payment`. Dispatch into `verticals/` and `domain/`; never contain business rules themselves.
  - `api/` — FastAPI routes and schemas. Thin — delegate to `application/`.
- `platform/` — feature-agnostic. Must not import from `features/` or contain airline/triage knowledge.
  - `ai/` — provider-agnostic LLM layer: `providers/` (anthropic, openai, `fallback`; decorators `budgeted` and `traced`), `budget.py` + `usage.py` (the LLM spend cap, ADR-0018), `embeddings.py`, structured-output schemas, `tool_loop.py`, streaming.
  - `guardrails/` — the one governance layer: `pii_filter` (+ `guarded_dispatcher`, which applies it to tool-call arguments; ADR-0013), `injection_detection`, `approval_gate` (+ `executing_store`, which runs an approved request's executor exactly once), `policy_engine` (OPA server client, fails closed) + `policy_checked_store` (checks `submit` against `policies/*.rego`; ADR-0015), `audit_log` (event model + sink protocol) with `audited_dispatcher` / `audited_store` (ADR-0016), `api_auth` (static bearer tokens per router; ADR-0019).
  - `mcp/` — `tool_bindings.py` wraps a `ToolRegistry` for MCP exposure without importing `features/`; `server.py` (a composition root) builds the registry from a feature (e.g. `claims_triage.tools.build_tool_registry()`) and hands it to `tool_bindings.py`. A subpackage, not a service (ADR-0003).
  - `infrastructure/` — Postgres, vector store, repositories, `audit_repository.py` (the append-only `audit_log` table).
  - `observability/` — logging, tracing (`tracing.py`, `traced_dispatcher.py`); `metrics.py` is a one-line placeholder.
  - `prompts/<feature>/vN.txt` — versioned prompts, see "Prompt versioning" below.

## Code style
Read `docs/code-style.md` before writing code — it holds the judgement-call rules (structure, types, where business rules live, docstrings, errors, tests). Formatting, lint and types are enforced by `make lint` (ruff + mypy strict); don't hand-argue what a tool already checks.

## Guardrails (non-negotiable)
Any tool that changes state (`log_claim`, `issue_payment`, an escalation) must pass through `platform/guardrails/approval_gate.py` and be checked against `platform/guardrails/policy_engine.py`. A tool being registered and callable is not the same as having permission to execute — this boundary is the one thing not to relax for build-speed during the sprint. Per ADR-0009, a state-changing tool call only *submits* a payload-bound approval request (server-issued `claim_id`, rules-derived values — never model-authored ones); execution happens exactly once, after a human approves (`ExecutingApprovalStore.approve` runs the executor, then wins `APPROVED → EXECUTED`), never inline in the tool. The store and tool registry are chosen by the composition roots and injected; there is no module-level gate. The API routes themselves sit behind static bearer tokens, one per role, so the caller that submits a request cannot approve it (ADR-0019).

## Prompt versioning
Prompts are versioned files under `src/ombuds/platform/prompts/<feature>/vN.txt` (currently `claims_triage/v4.txt` is live, with `v1`–`v3` kept as history), never inline strings. Bump the version rather than overwriting when wording changes meaningfully. A new version must run clean against `evals/datasets/` before it becomes the active version referenced in `config.py`. Record which version is live per environment in `.env.example`.

## Diagrams
Every diagram has one versioned page in `docs/diagrams/` (index and template there; rules in `docs/code-style.md`). ADRs and `architecture.md` link to it, never paste it.

## Decisions
Architecture decisions live in `docs/decisions/` as ADRs — start from `docs/decisions/0000-template.md`. Write one when choosing between real alternatives (a framework, a storage engine, a deployment shape), not for routine implementation choices.

## Testing
- `tests/unit/` mirrors `src/ombuds/` (`domain/`, `features/…`, `platform/…`) — one test module per source module, no I/O.
- `tests/integration/` — real Postgres/vector store via Docker, real MCP round-trip; mock the LLM provider.
- `tests/e2e/` — one-line placeholders, no real tests yet. The full-stack run is done by hand; the recipe and last result are in `docs/reports/e2e-report-2026-10-26.md`.
- `evals/` is not `tests/` — it measures agent/RAG quality against `evals/datasets/*.jsonl`, not pass/fail correctness. A failing eval shouldn't fail CI by itself, but a score regression should block a prompt or model change from merging.

## Security
Never commit real claim data, API keys, or `.env` — only `.env.example`. PII stays inside `platform/guardrails/pii_filter.py`'s reach (redacted at the use-case seams, tool dispatch, MCP and logs — ADR-0013); don't log raw evidence payloads in `platform/observability/logging.py`.
