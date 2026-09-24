# ADR-0004: EU261 domain tool set over generic helpdesk tools

**Status:** accepted
**Date:** 2026-09-24

## Context
The original study plan named generic support-desk tools (`create_ticket`, `check_sla`, `escalate_ticket`), while the README, AGENTS.md and the scaffold commit to an airline EU261 vertical with `check_eligibility`, `log_claim`, `issue_payment` and `search_kb`. Building both would split the demo into two stories. The generic set is quicker to invent, but its "rules" (SLA thresholds) are arbitrary, and none of its actions move money — so the approval gate would be guarding nothing anyone cares about.

## Decision
Build only the EU261 tool set; the generic ticket tools are dropped, and the study-plan tasks are renamed to match.

## Consequences
- `check_eligibility` wraps a real, externally verifiable rule set (Regulation (EC) 261/2004), so its unit tests assert against published law, not invented numbers.
- `issue_payment` gives the approval gate a meaningful target: real money, obvious need for a human.
- Build order constraint: the deterministic rules (`verticals/airline/rules.py`) come first, before any LLM loop, because `check_eligibility` is a thin wrapper around them.
- `issue_payment` is not registered with the agent or MCP until `platform/guardrails/approval_gate.py` exists — at minimum as a deny-all stub. Callable must never precede permitted, even temporarily.
- The rules model a deliberately simplified subset of EU261 (see `rules.py` docstring). Revisit if an eval case needs a rule outside that subset — extend `rules.py`, never patch around it in a prompt.

## Alternatives considered
- **Generic helpdesk tools (`create_ticket`, `check_sla`)** — faster to stub, but arbitrary rules and no money-moving action undercut the core "callable ≠ permitted" claim.
- **Both sets** — twice the tools to test and explain for no additional skill demonstrated.
