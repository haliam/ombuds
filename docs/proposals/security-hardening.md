# Plan: Security hardening for the public repo

**Status: proposed (2026-10-20).** Nothing here is implemented yet.

## Context
The repo is public. A secret scan of the working tree and the full git history (all branches) found no leaked keys: no Anthropic, OpenAI, AWS, GitHub, Google or Slack key patterns and no private keys. `.env` is gitignored and was never committed; `.env.example` has empty key values. The scan was a pattern grep, not gitleaks, so it will not catch keys in unusual formats.

It did find gaps that matter once the stack is reachable from outside localhost:
- **No API authentication.** No auth, bearer token or CORS handling exists in `src/`. Worse, `POST /approvals/{id}/approve` and `/deny` ([platform/guardrails/api.py](../../src/ombuds/platform/guardrails/api.py)) are open, so anyone who reaches port 8000 can approve a payment and defeat the human-approval gate (ADR-0009). `/triage` is open too, so anyone can spend the LLM budget (ADR-0018 caps the damage, it does not prevent it).
- **Compose publishes ports on all interfaces:** 5433 (Postgres, password `ombuds`), 8181 (OPA, unauthenticated) and 8000 (API).
- **Weak credential defaults.** `ombuds:ombuds` is hardcoded in `docker-compose.yml`, `.env.example` and as the fallback in `config.py` (`DATABASE_URL`). A deployment that forgets to set it silently uses the weak password.
- **No automated leak guard.** Pre-commit has `detect-private-key` only; there is no `.github/workflows` and no secret scanning.

## Order
One task per chat, one commit per task (AGENTS.md). Cheapest and most exposed first.

### 1. Bind compose ports to localhost
`docker-compose.yml`: `127.0.0.1:5433:5432`, `127.0.0.1:8181:8181`, `127.0.0.1:8000:8000`. No code change. OPA has no auth, so it must never be reachable from outside the host.

### 2. Secret-scanning guardrails
- Add a gitleaks hook to `.pre-commit-config.yaml` (alongside `detect-private-key`).
- Enable GitHub secret scanning and push protection in the repo settings (manual, free for public repos).
- Optional: a `.github/workflows` job running gitleaks on pull requests.
- One-off: run `gitleaks detect` over the full history to back up the grep-based scan.

### 3. Authenticate the API
- A bearer-token dependency on the routers, wired in the composition root `api_app.py`; tokens read from env (new settings in `config.py` and `.env.example`).
- Separate credentials for the triage endpoints and for approve/deny, so the caller that submits a request cannot approve it.
- Fail closed when unset, except under an explicit dev flag.
- Needs an ADR: static token vs JWT/OIDC vs authentication at a reverse proxy.
- Tests: no token returns 401, a triage token on approve returns 403; update the existing flow tests.

### 4. Remove the weak default DB credential
- `config.py`: require `DATABASE_URL` unless the dev flag is set.
- `docker-compose.yml`: take `POSTGRES_PASSWORD` and the container `DATABASE_URL` from `.env`; update `.env.example` and `docs/commands.md`.

### 5. Housekeeping
- Skim `docs/diagrams/*.html` for internal paths or hostnames (the scan found only false positives).
- Confirm spend limits are set in the provider consoles (manual).

Out of scope: rotating keys (none leaked) and rewriting history (nothing to purge).

## Verification
- Task 1: `make up`, then `ss -ltn` shows 5433, 8181 and 8000 bound to 127.0.0.1 only.
- Task 2: commit a dummy `sk-ant-...` string and confirm the hook blocks it; `gitleaks detect` is clean on history.
- Task 3: `make test` and `make test-integration`; `curl` without a token gets 401, and a triage token cannot call approve.
- Task 4: start the API with `DATABASE_URL` unset and confirm it refuses to start.
- After every task: `make test` (ruff, mypy strict, unit) is green before the commit.
