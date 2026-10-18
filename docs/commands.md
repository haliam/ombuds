# Commands

Day-to-day commands for working on ombuds. Run `make help` for the live list of targets. The `make` targets are defined in the [Makefile](../Makefile); the rest are tools you run directly.

## Run the app

| Command | What it does |
|---|---|
| `make up` | Builds and starts the full stack: db, one-shot migrate + KB ingest, then the API on `localhost:8000`. Needs `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in `.env`. |
| `make down` | Stops and removes the containers. The Postgres volume (and so all data) is kept. |
| `make run` | Starts Postgres, then the API on `:8000` outside Docker with auto-reload. Needs the keys in `.env`. |
| `make db-up` / `make db-down` | Starts / stops Postgres only (host port 5433). `db-down` is the same command as `down`. |
| `make logs` / `make ps` | Follow the API logs / show running containers. |
| `uv run python -m ombuds.platform.mcp.server` | Standalone MCP server over stdio. Needs the db up. |

Once the API is up:

| URL | What |
|---|---|
| `/scalar` | Scalar API reference (loads its script from a CDN, so it needs internet) |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | Raw OpenAPI schema |

## Test and quality

| Command | What it does |
|---|---|
| `make test` | Lint, then unit tests. Run before every commit. |
| `make lint` | `ruff check`, `ruff format --check` and `mypy`. |
| `make format` | Auto-fix lint issues and formatting. |
| `make test-integration` | Starts the db, then runs `tests/integration` against real Postgres. |
| `uv run pytest tests/unit/test_api_app.py -k scalar` | Run one test file, or filter by name. |

## Data and evals

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

## Setup

| Command | What it does |
|---|---|
| `uv sync` | Installs dependencies. `make` targets do this automatically on first run. |
| `uv run pre-commit install` | One-time. Runs the same checks on every commit. |
