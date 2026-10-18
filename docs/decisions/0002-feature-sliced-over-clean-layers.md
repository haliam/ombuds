# ADR-0002: Feature-sliced over clean layers

**Status:** accepted
**Date:** 2026-09-23

## Context
The first sketch of the repo was a horizontal, clean-architecture layout: top-level `domain/`, `verticals/`, `ai/`, `agent/`, `rag/`, `tools/`, `guardrails/`, `mcp/`, `infrastructure/`, `api/`. With that layout, one feature (claims triage) is spread across seven or more top-level folders, and it's hard to tell which code belongs to the feature and which is reusable plumbing. The system is meant to grow by adding capabilities (triage now, possibly others later), so the layout needed to show where a feature ends.

## Decision
Organise `src/ombuds/` into three areas: `domain/` (shared business models), `features/<feature>/` (everything specific to one capability, sliced vertically), and `platform/` (feature-agnostic infrastructure that any feature can use).

## Consequences
- Everything specific to claims triage (agent graph, RAG, tools, airline rules, API routes, use case) lives under `features/claims_triage/`. It can be read, tested and reasoned about as one unit.
- `platform/` (LLM providers, guardrails, MCP, persistence, observability, prompts) has to stay generic. If airline or triage knowledge leaks into it, that's a bug.
- Import direction is enforced by convention only: `features → platform → domain`. The only places that wire features into platform are the composition roots, `api_app.py` and the MCP server entrypoint.
- Harder: some concerns sit on the boundary. Guardrails are platform, but the payout rules they enforce are feature-specific (`features/claims_triage/application/policies.py`, `.rego` in `platform/guardrails/policies/`). Each such case needs a deliberate choice.
- Revisit if a second feature ends up copying large parts of `features/claims_triage/`. That would mean some of it belongs in `platform/`.

## Alternatives considered
- **Horizontal clean layers** (the original sketch): layer boundaries are crisp, but feature cohesion is poor, and a lone vertical gets smeared across the whole tree.
- **One flat package**: fine for a week, but it doesn't make the governance boundary (`platform/guardrails`) or the feature boundary visible, and both are central to the story this project tells.

See the layering and composition-root diagram in [architecture.md](../diagrams/layering/README.md).
