# ADR-0018: Process-wide LLM spend cap in a provider decorator

**Status:** accepted
**Date:** 2026-10-18

## Context
Before the first real end-to-end run, nothing bounded spend except `MAX_TOOL_TURNS` and a fixed output cap per turn. A loop bug, a retry storm or a looping client could burn money, and `ProviderTurn` carried no token usage, so nothing could be metered.

## Decision
- **Usage on the turn.** `ProviderTurn` and `TurnDone` carry a provider-agnostic `TokenUsage`; `AnthropicProvider` fills it (cache reads and writes count as input).
- **A ledger and a decorator.** `UsageBudget` keeps running tokens and estimated USD (a price table in `config.py`; unknown models are charged at a high price). `BudgetedProvider` wraps each concrete adapter, refuses a turn with `BudgetExceededError` once either cap is reached, and charges the reported usage after the turn. It sits inside `TracedProvider` and outside nothing else, so a failover is charged at the fallback model's price.
- **One ledger per process**, from `process_budget()`, because `run_triage` builds a provider per request. Caps are `LLM_BUDGET_MAX_USD` (default 1.00) and `LLM_BUDGET_MAX_TOKENS` (default 500000).
- **HTTP behaviour.** `BudgetExceededError` becomes a 429 from the app, or an `error` frame on the SSE stream. `FallbackProvider` does not catch it, so it never fails over to a cheaper model.
- **Output cap** is configurable (`ANTHROPIC_MAX_TOKENS`, default 4096, raised from 1024 because truncation means escalation).

## Consequences
- Safe by default: a fresh checkout cannot spend more than the default caps per process.
- The ledger is an estimate and resets on restart; each worker has its own. The provider-side spend limit remains the real backstop, and should be set.
- In-flight turns are not reserved, so concurrent requests can overshoot by the turns already running.
- Embedding calls (OpenAI) are not metered; they cost cents for the seed KB.
- Not done: a persistent (Postgres) or per-claimant ledger. Add one if the system is ever shared.

## Alternatives considered
- **Only a provider-console limit:** it stops spend but gives no clean error to the caller and cannot be tested.
- **Per-request cap only:** `MAX_TOOL_TURNS` already bounds one run; the risk is many runs.
- **Postgres-backed ledger:** survives restarts but needs a migration and a transaction per turn; not worth it for a single-process demo.
