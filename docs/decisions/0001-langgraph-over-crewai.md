# ADR-0001: LangGraph over CrewAI/AutoGen for orchestration

**Status:** accepted
**Date:** 2026-09-23

## Context
The claims-triage agent needs explicit control over routing: call the model, run tools, check the answer, repair or escalate. State-changing actions need a human-approval gate. The target role's required skills also name CrewAI, AutoGen, Semantic Kernel, OpenAI Agents SDK, and Google ADK as acceptable frameworks, so the choice needed a defensible reason beyond familiarity.

The original draft of this ADR also expected LangGraph to provide persistent checkpointing and to host the approval gate as a node. Neither happened (see Consequences): durable state and approval live in Postgres, outside the graph.

## Decision
Use LangGraph as the orchestration layer for the agent's **tool-calling loop only**. The graph (`agent/graph.py`) has four nodes: `call_model`, `dispatch_tools`, `finalize` and `escalate`. It owns the model turn, tool dispatch, output repair and escalation when a run cannot converge.

The graph does **not** own the claim lifecycle, eligibility, approval or payment:
- Eligibility comes from deterministic rules (`verticals/airline/rules.py`) via tools. `verify_decision` checks the model's answer against the rules result.
- A state-changing tool call only submits a payload-bound approval request (ADR-0009). The graph ends there. A human approves later through the API, and `ExecutingApprovalStore` runs the executor exactly once.
- Policy is checked by OPA (ADR-0015) and every governed action is audited (ADR-0016), both outside the graph.

## Consequences
- Routing is code, not emergent behavior from role-played conversation between agents. It is easy to explain, audit and unit-test: one node, one test.
- The graph is thin. It is the earlier hand-rolled `for` loop expressed as nodes and conditional edges, so LangGraph is a modest gain over a plain loop, not a necessity. Because governance sits outside it, the graph could be replaced by a plain loop or a workflow engine without touching guardrails.
- **No checkpointing.** `graph.compile()` takes no checkpointer and no node uses `interrupt`. A run is short-lived, and a crash mid-run means the request is retried. Durable state is the approval store in Postgres, not LangGraph state.
- **No approval node.** The human pause is asynchronous and lives outside the run, which keeps it correct across restarts and multiple workers.
- Classify, retrieve and decide are not separate nodes. They happen inside the model's tool loop and `finalize`.
- Gives up some of the "batteries included" convenience CrewAI/AutoGen offer for quick multi-agent demos. That is not needed, since this is one agent making tool calls, not a crew of agents with independent goals.
- Revisit if the system grows a genuine need for multiple cooperating agents, or a long-running investigation that must wait (for example days for missing evidence) and resume. That would justify a checkpointer plus `interrupt`, or Temporal.

The resulting graph (nodes, counters and escalation paths) is drawn in [ADR-0005](0005-prompted-json-with-repair-over-native-structured-output.md#the-triage-graph-end-to-end).

Diagram: [LangGraph Triage Loop v1.0](../diagrams/triage-graph/README.md)

## Alternatives considered
- **CrewAI / AutoGen** — role-based/conversable agent abstractions fit multi-agent collaboration better than a single agent with a strict approval gate; state and control flow are less explicit than a state graph.
- **A plain Python loop** — all the graph does today. Kept LangGraph for explicit, separately testable nodes and a conventional framework story, accepting that it adds a dependency for little current gain.
- **Semantic Kernel** — strong enterprise/.NET integration story, worth knowing conceptually for the interview, but the Python-first LangGraph ecosystem matched the rest of this stack better.
- **OpenAI Agents SDK / Google ADK** — more provider-coupled; LangGraph's model-agnostic design matched the multi-provider fallback already planned in `platform/ai/providers/`.
