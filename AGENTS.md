# AGENTS.md — ombuds

## Project overview
`ombuds` is a governed, observable agentic claims-triage system. The first (and currently only) vertical is airline EU261 refund/compensation claims. Python + FastAPI + LangGraph agent, RAG over airline policy docs, tools exposed both directly and via MCP, guardrails (PII filtering, injection detection, approval gates, OPA/Rego policy) in front of any state-changing action.

Built as a 4-week interview-prep capstone for an AI/Agentic Engineer role. See `docs/architecture.md` for the business framing and `docs/decisions/` for why things are shaped the way they are — check there before re-litigating a decision that's already been made.

## Stack
Python ≥3.11 · FastAPI · LangGraph · MCP · PostgreSQL + pgvector (or Chroma) · OpenTelemetry · OPA/Rego · Docker Compose · pytest

## Commands
Keep this section accurate or delete a stale line — a wrong command here is worse than no command.
**Status (2026-09-24):** only `make test`, `make lint` and `make format` are wired; `up` and `eval` are still no-op placeholders. Add a command here only once it actually works.
- `make test` → `make lint` then `uv run pytest tests/unit` (uv creates `.venv` and installs deps on first run)
- `make lint` → `ruff check` + `ruff format --check` + `mypy`; `make format` → ruff auto-fix. Config in `pyproject.toml`
- `uv run pre-commit install` → one-time, runs the same checks on every commit
- Planned: `make eval` → `python evals/run_evals.py`, `make up` → `docker compose up`
- Planned: MCP standalone → `python -m ombuds.platform.mcp.server`; API app factory lives in `src/ombuds/api_app.py`

## Layout (feature-sliced — see ADR-0002)
`src/ombuds/` has three areas. Import direction is `features → platform → domain`; never the reverse. The only modules allowed to wire a feature into platform are the composition roots: `api_app.py` and the MCP server entrypoint.

- `domain/` — shared business models (`models/claim.py`, `enums.py`) and `errors.py`. No LLM, agent, HTTP or DB concerns.
- `features/claims_triage/` — everything specific to the one feature:
  - `verticals/airline/` — `rules.py` (EU261 tiers, exemptions), `evidence_schema.py`, `kb_seed/`. Only `airline/` exists; no vertical registry/ABC until a second one does.
  - `application/` — `triage_use_case.py` (orchestrates a triage) and `policies.py` (feature-specific approval rules).
  - `agent/` — LangGraph `graph.py`, `state.py`, `nodes/` (classify, retrieve, decide, escalate_retry), `memory/`.
  - `rag/` — chunking, embeddings, ingest, retrieval, citation.
  - `tools/` — `search_kb`, `check_eligibility`, `log_claim`, `issue_payment`. Dispatch into `verticals/` and `domain/`; never contain business rules themselves.
  - `api/` — FastAPI routes and schemas. Thin — delegate to `application/`.
- `platform/` — feature-agnostic. Must not import from `features/` or contain airline/triage knowledge.
  - `ai/` — provider-agnostic LLM layer: `providers/` (anthropic, openai, fallback), structured-output schemas, `tool_loop.py`, streaming.
  - `guardrails/` — the one governance layer: `pii_filter`, `injection_detection`, `approval_gate`, `policy_engine` + `policies/*.rego`.
  - `mcp/` — `tool_bindings.py` wraps a `ToolRegistry` for MCP exposure without importing `features/`; `server.py` (a composition root) builds the registry from a feature (e.g. `claims_triage.tools.build_tool_registry()`) and hands it to `tool_bindings.py`. A subpackage, not a service (ADR-0003).
  - `infrastructure/` — Postgres, vector store, repositories, audit log.
  - `observability/` — logging, tracing, metrics.
  - `prompts/<feature>/vN.txt` — versioned prompts, see "Prompt versioning" below.

## Code style
Read `docs/code-style.md` before writing code — it holds the judgement-call rules (structure, types, where business rules live, docstrings, errors, tests). Formatting, lint and types are enforced by `make lint` (ruff + mypy strict); don't hand-argue what a tool already checks.

## Guardrails (non-negotiable)
Any tool that changes state (`log_claim`, `issue_payment`, an escalation) must pass through `platform/guardrails/approval_gate.py` and be checked against `platform/guardrails/policy_engine.py`. A tool being registered and callable is not the same as having permission to execute — this boundary is the one thing not to relax for build-speed during the sprint.

## Prompt versioning
Prompts are versioned files under `src/ombuds/platform/prompts/<feature>/vN.txt` (currently `claims_triage/v1.txt`, `v2.txt`), never inline strings. Bump the version rather than overwriting when wording changes meaningfully. A new version must run clean against `evals/datasets/` before it becomes the active version referenced in `config.py`. Record which version is live per environment in `.env.example`.

## Decisions
Architecture decisions live in `docs/decisions/` as ADRs — start from `docs/decisions/0000-template.md`. Write one when choosing between real alternatives (a framework, a storage engine, a deployment shape), not for routine implementation choices.

## Testing
- `tests/unit/` mirrors `src/ombuds/` (`domain/`, `features/…`, `platform/…`) — one test module per source module, no I/O.
- `tests/integration/` — real Postgres/vector store via Docker, real MCP round-trip; mock the LLM provider.
- `tests/e2e/` — full `docker compose up` stack; may hit a real or recorded LLM response.
- `evals/` is not `tests/` — it measures agent/RAG quality against `evals/datasets/*.jsonl`, not pass/fail correctness. A failing eval shouldn't fail CI by itself, but a score regression should block a prompt or model change from merging.

## Security
Never commit real claim data, API keys, or `.env` — only `.env.example`. PII stays inside `platform/guardrails/pii_filter.py`'s reach; don't log raw evidence payloads in `platform/observability/logging.py`.
