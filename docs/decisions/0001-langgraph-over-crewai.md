# ADR-0001: LangGraph over CrewAI/AutoGen for orchestration

**Status:** accepted
**Date:** 2026-09-23

## Context
The claims-triage agent needs explicit control over routing (classify → retrieve → decide → act), a human-approval gate before any state-changing action, and persistent checkpointing so a claim's in-flight state survives a restart. The target role's required skills also name CrewAI, AutoGen, Semantic Kernel, OpenAI Agents SDK, and Google ADK as acceptable frameworks, so the choice needed a defensible reason beyond familiarity.

## Decision
Use LangGraph as the orchestration layer for the agent.

## Consequences
- The explicit state graph makes the human-in-the-loop approval gate and checkpointing straightforward to reason about and unit-test in isolation — one node, one test.
- Routing logic is code, not emergent behavior from role-played conversation between agents. That's easier to explain and audit, which matters directly for the governance/guardrails story this project is built around.
- Gives up some of the "batteries included" convenience CrewAI/AutoGen offer for quick multi-agent demos — not needed here, since this is one agent making tool calls, not a crew of agents with independent goals.
- Revisit if the system grows a genuine need for multiple cooperating agents rather than one agent routing through sequential steps.

The resulting graph (nodes, counters and escalation paths) is drawn in [ADR-0005](0005-prompted-json-with-repair-over-native-structured-output.md#the-triage-graph-end-to-end).

## Alternatives considered
- **CrewAI / AutoGen** — role-based/conversable agent abstractions fit multi-agent collaboration better than a single agent with a strict approval gate; state and control flow are less explicit than a state graph.
- **Semantic Kernel** — strong enterprise/.NET integration story, worth knowing conceptually for the interview, but the Python-first LangGraph ecosystem matched the rest of this stack better.
- **OpenAI Agents SDK / Google ADK** — more provider-coupled; LangGraph's model-agnostic design matched the multi-provider fallback already planned in `platform/ai/providers/`.
