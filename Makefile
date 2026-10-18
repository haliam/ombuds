.PHONY: help up down logs ps run lint format test db-up db-down db-reset test-integration test-policy opa-up ingest eval

help: # list the targets and what they do
	@grep -E '^[a-z-]+:.*# ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):[^#]*# (.*)/\1\t\2/' | column -t -s "$$(printf '\t')"

up: # full stack: db, one-shot migrate + ingest, api on :8000 (needs keys in .env)
	docker compose up --build -d --wait

down: # stop the stack; the Postgres volume is kept
	docker compose down

logs: # follow the API logs
	docker compose logs -f api

ps: # show which containers are running
	docker compose ps

run: db-up # API on :8000 with auto-reload, outside Docker (needs keys in .env)
	uv run uvicorn ombuds.api_app:app --reload

lint: # ruff check + format check + mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format: # auto-fix lint and formatting
	uv run ruff check --fix .
	uv run ruff format .

test: lint # lint, then unit tests
	uv run pytest tests/unit

db-up: # Postgres + pgvector for dev and integration tests
	docker compose up -d --wait db

db-down: # stop the stack; the Postgres volume is kept
	docker compose down

db-reset: # DESTRUCTIVE: stop the stack and delete the Postgres volume
	docker compose down -v

test-integration: db-up opa-up # integration tests against real Postgres and OPA
	uv run pytest tests/integration -m integration

opa-up: # OPA policy server on :8181 for dev and integration tests
	docker compose up -d opa

test-policy: # opa check + the Rego unit tests, run in the OPA container
	docker compose run --rm --no-deps -v $(CURDIR)/src/ombuds/platform/guardrails/policies:/p:ro --entrypoint opa opa check --strict /p
	docker compose run --rm --no-deps -v $(CURDIR)/src/ombuds/platform/guardrails/policies:/p:ro --entrypoint opa opa test /p

ingest: db-up # chunk + embed the KB seed documents into pgvector (needs OPENAI_API_KEY)
	uv run python -m ombuds.features.claims_triage.rag.ingest

eval: ingest # retrieval eval over the ingested KB: metrics per relevance floor (needs OPENAI_API_KEY)
	uv run python -m evals.run_evals
