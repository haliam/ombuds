# ADR-0003: MCP as a subpackage, not a standalone service

**Status:** accepted
**Date:** 2026-09-23

## Context
The target role requires hands-on MCP experience, and the agent's tools (`search_kb`, `check_eligibility`, `log_claim`, `issue_payment`) need to be reachable both as direct Python calls (for tests and the eval harness) and over MCP (to demonstrate the protocol boundary a real enterprise integration would use). Running MCP as a fully separate deployable service is closer to a real production shape, but adds real operational cost — its own container, health checks, network hop — for a solo build on a 4-week clock.

## Decision
Expose tools over MCP from `platform/mcp/server.py`, runnable standalone (`python -m ombuds.platform.mcp.server`), but ship it as a subpackage of the same codebase rather than a second top-level project or service.

## Consequences
- One repo, one Docker Compose stack, one CI pipeline for the timeline available — the MCP boundary is demonstrated without doubling deployment surface area.
- `platform/mcp/tool_bindings.py` is the single place that wraps feature tools (`features/claims_triage/tools/`) for MCP exposure, so tools stay directly usable (by the agent, by tests, by evals) without going through MCP every time. MCP is one boundary into the tools, not the only path.
- Because feature tools never import `platform/mcp/`, MCP can be extracted into its own service later without touching the tools or `domain/` if a real multi-consumer scenario ever needs it.
- Be ready to state in the interview *why* this is a subpackage today and what would change if it needed to serve multiple independent agent consumers — that's the actual trade-off being tested, not whether MCP was used at all.

## Alternatives considered
- **Standalone MCP microservice** — closer to a real enterprise deployment shape, but the added container/networking/CI surface wasn't worth it for a solo capstone on this timeline. The reasoning for when it *would* be worth it transfers even without building it.
