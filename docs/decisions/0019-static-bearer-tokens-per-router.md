# ADR-0019: Static bearer tokens, one per role, attached to the routers

**Status:** accepted
**Date:** 2026-10-22

## Context
Until now anyone who could reach port 8000 could triage claims (spending LLM budget) and approve their own payment requests, and the approver recorded in the audit trail was a string the caller typed. The human approval gate (ADR-0009) is only a control if the caller who submits a request cannot also approve it. The options were a static shared secret per role, JWT/OIDC, or authentication at a reverse proxy.

## Decision
- **Two static bearer tokens**, `OMBUDS_TRIAGE_TOKEN` for `/claims/*` and `OMBUDS_APPROVER_TOKEN` for `/approvals*` (the reads too, since pending payloads hold claim data). A token for one role used on the other's endpoints gets 403; a missing or unknown token gets 401.
- **The approver comes from config**, `OMBUDS_APPROVER`, and is injected by the dependency. `approver` is removed from the request body, and a body that still sends it is rejected (422) rather than silently ignored.
- **Fail closed, no dev bypass.** If any of the three settings is empty, or the two tokens are equal, protected endpoints answer 503 and log why. Settings are read per request (`config.api_auth()`), not at import, so the app still starts and tests can cover the unset case. Local use sets the tokens in `.env`.
- **Attached to the routers**, not the app: `require_triage_token` and `require_approver_token` (`platform/guardrails/api_auth.py`) are `dependencies=[...]` on each `APIRouter`. `/openapi.json`, `/docs`, `/redoc` and `/scalar` stay public; compose's healthcheck fetches `/openapi.json` and must not need a secret. The schema describes the API but exposes no data.
- Tokens are compared with `secrets.compare_digest`.

## Consequences
- The submitter and the approver are different credentials, so a leaked or misused triage token cannot release money.
- All approvers share one token and one recorded name, so the audit trail says "the approver role", not which person. Rotating a token is a config change and a restart.
- The MCP server is a stdio subprocess of a trusted caller and is not covered; it shares the Postgres-backed approvals but `approve` is not exposed as a tool.
- Tokens travel in plain HTTP; TLS is the operator's job (ports bind to 127.0.0.1, see compose).
- Revisit when there is more than one human approver, or an external caller: per-person identity needs JWT/OIDC.

## Alternatives considered
- **JWT/OIDC:** gives per-person identity and expiry, but needs an identity provider and key handling that a single-operator demo does not justify.
- **Authentication at a reverse proxy:** keeps the app free of auth code, but the app would then trust a header and the approver/triage split would live outside the repo and its tests.
- **One token with a role claim in the body:** the caller picks its own role, which defeats the separation.
- **A dev flag that disables auth:** one environment variable away from an open payment API; setting two tokens in `.env` is cheap enough.
