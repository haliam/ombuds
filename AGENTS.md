# AGENTS.md — ombuds

## Project overview
`ombuds` is a governed, observable agentic claims-triage system. The first (and currently only) vertical is airline EU261 refund/compensation claims. Python + FastAPI + LangGraph agent, RAG over airline policy docs, tools exposed both directly and via MCP, guardrails (PII filtering, injection detection, approval gates, OPA/Rego policy) in front of any state-changing action.

Built as a 4-week interview-prep capstone for an AI/Agentic Engineer role. See `docs/architecture.md` for the business framing and `docs/decisions/` for why things are shaped the way they are — check there before re-litigating a decision that's already been made.

## Stack
Python ≥3.11 · FastAPI · LangGraph · MCP · PostgreSQL + pgvector (or Chroma) · OpenTelemetry · OPA/Rego · Docker Compose · pytest

## Commands
Keep this section accurate or delete a stale line — a wrong command here is worse than no command.
**Status (2026-10-15):** `make test-policy`, `make opa-up`, `make test`, `make lint`, `make format`, `make db-up`/`db-down`, `make test-integration`, `make ingest`, `make eval`, `make eval-agent`, `make up` and `make down` are wired. Add a command here only once it actually works.
- Developer guide (run, debug, commands, working rules): `docs/guide/developer-guide.md`; `make help` lists the targets. Also wired: `make logs`, `make ps`, `make run` (API with reload, outside Docker) and `make db-reset` (destructive: deletes the Postgres volume).
- `make test` → `make lint` then `uv run pytest tests/unit` (uv creates `.venv` and installs deps on first run)
- `make lint` → `ruff check` + `ruff format --check` + `mypy`; `make format` → ruff auto-fix. Config in `pyproject.toml`
- `make db-up` → `docker compose up -d --wait db` (Postgres + pgvector on host port 5433); needs `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env` (no default password; `OMBUDS_ALLOW_DEV_DEFAULTS=1` opts in to a dev URL for the app); `make test-integration` starts it and runs `tests/integration`
- `make ingest` → starts the db, then chunks + embeds `verticals/airline/kb_seed/*.md` into pgvector (needs `OPENAI_API_KEY`); safe to re-run
- `make test-policy` → `opa check` + Rego unit tests (`*_test.rego`) in the OPA container; `make opa-up` starts the OPA server on :8181 (`make test-integration` does it too; `make up` includes it). `PAYOUT_LIMIT_EUR` (default 400) is the payout ceiling
- `OTEL_TRACES_EXPORTER=console` (or `otlp` + `OTEL_EXPORTER_OTLP_ENDPOINT`) → emit spans for LLM turns, tool calls and policy checks (ADR-0017); default `none`
- `uv run pre-commit install` → one-time, runs the same checks (plus gitleaks) on every commit
- `.github/workflows/ci.yml` → on PRs and `main`: `make test`, `make test-policy` + `tests/integration` (pgvector service + OPA container; under `CI` an unreachable service fails the suite instead of skipping), and a gitleaks scan. GitHub secret scanning push protection is enabled on the repo
- `make eval` → `make ingest`, then `python -m evals.run_evals`: retrieval hit@k/MRR per relevance floor over `evals/datasets/airline_retrieval.jsonl` (needs `OPENAI_API_KEY`; prints a report, never fails)
- `make eval-agent` → `make ingest`, then `python -m evals.run_agent_evals`: runs the real agent over `evals/datasets/airline_claims.jsonl` (claim text → expected outcome: decision, clarify or escalate; expected verdicts are computed from gold facts by the rules engine) and prints outcome/verdict accuracy plus the misses (needs `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`; costs money; never fails). Run it before making a new prompt version live
- `make up` → `docker compose up --build -d --wait`: db, a one-shot `migrate-ingest` (migrations + KB ingest, needs `OPENAI_API_KEY` in `.env`), then the API on `localhost:8000` (needs `ANTHROPIC_API_KEY` too); `make down` stops it.. Approvals live in Postgres, so the API holds no per-process approval state
- `python -m ombuds.platform.mcp.server` → the standalone MCP server over stdio (same Postgres-backed approvals as the API; needs the db up). API app factory: `create_app()` in `src/ombuds/api_app.py`

## Layout (feature-sliced — see ADR-0002)
`src/ombuds/` has three areas. Import direction is `features → platform → domain`; never the reverse. The only modules allowed to wire a feature into platform are the composition roots: `api_app.py` and the MCP server entrypoint.

- `domain/` — shared business models (`models/claim.py`, `enums.py`) and `errors.py`. No LLM, agent, HTTP or DB concerns.
- `features/claims_triage/` — everything specific to the one feature:
  - `verticals/airline/` — `rules.py` (EU261 tiers, exemptions), `evidence_schema.py`, `kb_seed/`. Only `airline/` exists; no vertical registry/ABC until a second one does.
  - `application/` — `triage_use_case.py` (orchestrates a triage), `runtime.py` (builds the Postgres-backed approval store + tool registry for a composition root), `executors.py` (what runs once a request is approved) and `policies.py` (empty scaffold for feature-specific approval rules).
  - `agent/` — LangGraph `graph.py` (the model/tool loop only: no checkpointer, no approval node; ADR-0001), `state.py`, `nodes/` (`escalate_retry` only — classify/retrieve/decide happen inside the model's tool loop and `finalize`), `memory/`.
  - `rag/` — chunking, embeddings, ingest, retrieval, citation.
  - `tools/` — `search_kb`, `check_eligibility`, `log_claim`, `issue_payment`. Dispatch into `verticals/` and `domain/`; never contain business rules themselves.
  - `api/` — FastAPI routes and schemas. Thin — delegate to `application/`.
- `platform/` — feature-agnostic. Must not import from `features/` or contain airline/triage knowledge.
  - `ai/` — provider-agnostic LLM layer: `providers/` (anthropic, openai, fallback), structured-output schemas, `tool_loop.py`, streaming.
  - `guardrails/` — the one governance layer: `pii_filter` (+ `guarded_dispatcher`, which applies it to tool-call arguments; ADR-0013), `injection_detection`, `approval_gate` (+ `executing_store`, which runs an approved request's executor exactly once), `policy_engine` (OPA server client, fails closed) + `policy_checked_store` (checks `submit` against `policies/*.rego`; ADR-0015), `audit_log` (event model + sink protocol) with `audited_dispatcher` / `audited_store` (ADR-0016).
  - `mcp/` — `tool_bindings.py` wraps a `ToolRegistry` for MCP exposure without importing `features/`; `server.py` (a composition root) builds the registry from a feature (e.g. `claims_triage.tools.build_tool_registry()`) and hands it to `tool_bindings.py`. A subpackage, not a service (ADR-0003).
  - `infrastructure/` — Postgres, vector store, repositories, `audit_repository.py` (the append-only `audit_log` table).
  - `observability/` — logging, tracing, metrics.
  - `prompts/<feature>/vN.txt` — versioned prompts, see "Prompt versioning" below.

## Code style
Read `docs/code-style.md` before writing code — it holds the judgement-call rules (structure, types, where business rules live, docstrings, errors, tests). Formatting, lint and types are enforced by `make lint` (ruff + mypy strict); don't hand-argue what a tool already checks.

## Guardrails (non-negotiable)
Any tool that changes state (`log_claim`, `issue_payment`, an escalation) must pass through `platform/guardrails/approval_gate.py` and be checked against `platform/guardrails/policy_engine.py`. A tool being registered and callable is not the same as having permission to execute — this boundary is the one thing not to relax for build-speed during the sprint. Per ADR-0009, a state-changing tool call only *submits* a payload-bound approval request (server-issued `claim_id`, rules-derived values — never model-authored ones); execution happens exactly once, after a human approves (`ExecutingApprovalStore.approve` runs the executor, then wins `APPROVED → EXECUTED`), never inline in the tool. The store and tool registry are chosen by the composition roots and injected; there is no module-level gate.

## Prompt versioning
Prompts are versioned files under `src/ombuds/platform/prompts/<feature>/vN.txt` (currently `claims_triage/v4.txt` is live, with `v1`–`v3` kept as history), never inline strings. Bump the version rather than overwriting when wording changes meaningfully. A new version must run clean against `evals/datasets/` before it becomes the active version referenced in `config.py`. Record which version is live per environment in `.env.example`.

## Diagrams
Every diagram has one versioned page in `docs/diagrams/` (index and template there; rules in `docs/code-style.md`). ADRs and `architecture.md` link to it, never paste it.

## Decisions
Architecture decisions live in `docs/decisions/` as ADRs — start from `docs/decisions/0000-template.md`. Write one when choosing between real alternatives (a framework, a storage engine, a deployment shape), not for routine implementation choices.

## Testing
- `tests/unit/` mirrors `src/ombuds/` (`domain/`, `features/…`, `platform/…`) — one test module per source module, no I/O.
- `tests/integration/` — real Postgres/vector store via Docker, real MCP round-trip; mock the LLM provider.
- `tests/e2e/` — full `docker compose up` stack; may hit a real or recorded LLM response.
- `evals/` is not `tests/` — it measures agent/RAG quality against `evals/datasets/*.jsonl`, not pass/fail correctness. A failing eval shouldn't fail CI by itself, but a score regression should block a prompt or model change from merging.

## Security
Never commit real claim data, API keys, or `.env` — only `.env.example`. PII stays inside `platform/guardrails/pii_filter.py`'s reach (redacted at the use-case seams, tool dispatch, MCP and logs — ADR-0013); don't log raw evidence payloads in `platform/observability/logging.py`.
