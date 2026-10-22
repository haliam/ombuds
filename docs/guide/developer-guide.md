# Developer guide

How to run, debug and work on ombuds day to day. Run `make help` for the live list of targets. The `make` targets are defined in the [Makefile](../Makefile); the rest are tools you run directly.

## First-time setup

1. `cp .env.example .env`, then fill in `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` (OpenAI is used for embeddings) and replace `change-me` with a password of your choice in both `POSTGRES_PASSWORD` and `DATABASE_URL` (URL-safe characters only). There is no default: compose refuses to start without `POSTGRES_PASSWORD`, and the app refuses to start without `DATABASE_URL`. `OMBUDS_ALLOW_DEV_DEFAULTS=1` opts in to a throwaway `ombuds:ombuds` URL for the app only. The password is applied when the Postgres volume is first created, so after changing it run `make db-reset`.
2. `uv sync` installs dependencies (`make` targets also do this on first run).
3. `uv run pre-commit install` runs the same checks on every commit.

## Run the app

Typical dev loop: `make opa-up`, `make ingest` (once), then `make run`. State-changing tools need OPA up, because the policy check fails closed.

| Command | What it does |
|---|---|
| `make run` | Starts Postgres, then the API on `:8000` outside Docker with auto-reload. Needs the keys in `.env`. |
| `make up` | Builds and starts the full stack: db, one-shot migrate + KB ingest, then the API on `localhost:8000`. Needs `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in `.env`. |
| `make down` | Stops and removes the containers. The Postgres volume (and so all data) is kept. |
| `make db-up` / `make db-down` | Starts / stops Postgres only (host port 5433). `db-down` is the same command as `down`. |
| `make logs` / `make ps` | Follow the API logs / show running containers. |
| `uv run python -m ombuds.platform.mcp.server` | Standalone MCP server over stdio. Needs the db up. |

Once the API is up:

| URL | What |
|---|---|
| `POST /claims/triage` | Triage a claim: body `{"claim_text": "..."}`. `/claims/triage/stream` is the streaming variant. |
| `/approvals` | List pending approvals; `GET /{id}`, `POST /{id}/approve`, `POST /{id}/deny`. A human approval is what executes a state-changing action. |
| `/scalar` | Scalar API reference (loads its script from a CDN, so it needs internet) |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | Raw OpenAPI schema |

## Debug

- `OTEL_TRACES_EXPORTER=console` prints spans for LLM turns, tool calls and policy checks to stderr (`otlp` plus `OTEL_EXPORTER_OTLP_ENDPOINT` ships them to a collector; ADR-0017).
- Every triage response carries `tool_results`, the list of each tool call the agent made.
- The append-only `audit_log` table in Postgres records every tool call and approval event. See [db-queries.md](db-queries.md) for read-only queries (`localhost:5433`, database and user `ombuds`, password from `POSTGRES_PASSWORD` in `.env`).
- One test with the debugger: `uv run pytest tests/unit/<file> -k <name> -x --pdb`.
- VS Code: there is no `launch.json` yet. To step through the API, add a launch config running uvicorn with `ombuds.api_app:create_app` and the `--factory` flag.
- If startup or ingest fails: `docker compose logs migrate-ingest`. OPA listens on `:8181`, Postgres on host port `5433`.

## Test and quality

| Command | What it does |
|---|---|
| `make test` | Lint, then unit tests. Run before every commit. |
| `make lint` | `ruff check`, `ruff format --check` and `mypy`. |
| `make format` | Auto-fix lint issues and formatting. |
| `make test-integration` | Starts the db, then runs `tests/integration` against real Postgres. |
| `uv run pytest tests/unit/test_api_app.py -k scalar` | Run one test file, or filter by name. |

## Data, policy and evals

| Command | What it does |
|---|---|
| `make opa-up` | Starts the OPA policy server on :8181 (ADR-0015). |
| `make test-policy` | `opa check --strict` and the Rego unit tests, run in the OPA container. |
| `make ingest` | Chunks and embeds `verticals/airline/kb_seed/*.md` into pgvector. Needs `OPENAI_API_KEY`. Safe to re-run. |
| `make eval` | Runs ingest, then prints retrieval metrics. Never fails the build. |

## Docker

| Command | What it does |
|---|---|
| `docker compose logs migrate-ingest` | Output of the migrate + ingest step. |
| `make db-reset` | **Destructive.** Stops everything and deletes the Postgres volume (`docker compose down -v`). All claims and approvals are lost. |

## Working rules

- **Layering:** imports go `features → platform → domain`, never the reverse. Only `api_app.py` and the MCP server entrypoint wire a feature into platform (ADR-0002).
- **Guardrails:** a state-changing tool only *submits* an approval request; execution happens once, after a human approves (ADR-0009). Never bypass the approval gate or the OPA check.
- **Prompts:** versioned files in `src/ombuds/platform/prompts/claims_triage/` (v4 is live). Bump the version rather than editing in place, and run the evals first.
- **Limits:** `LLM_BUDGET_MAX_USD` / `LLM_BUDGET_MAX_TOKENS` cap LLM spend per process (ADR-0018); `PAYOUT_LIMIT_EUR` (default 400) caps payouts.
- **Secrets:** never commit `.env` or real claim data; only `.env.example`.
- **Read first:** [code-style.md](code-style.md), the ADRs in [decisions/](decisions/), and [architecture.md](architecture.md).
- **Workflow:** one commit per plan task, then stop; the next task goes in a new chat.
