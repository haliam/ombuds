up: # will eventually run docker compose up
	@true

down: # will eventually run docker compose down
	@true

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format:
	uv run ruff check --fix .
	uv run ruff format .

test: lint
	uv run pytest tests/unit

db-up: # Postgres + pgvector for dev and integration tests
	docker compose up -d --wait db

db-down:
	docker compose down

test-integration: db-up
	uv run pytest tests/integration -m integration

eval: # will eventually run evals/run_evals.py
	@true
