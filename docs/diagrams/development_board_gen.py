import json
import sys

W = 146
lanes = [
    ("start_d", "Project start · decisions"),
    ("w1_d", "Week 1 · decisions"),
    ("w1_d2", "Week 1 · decisions (2)"),
    ("w1", "Week 1 · build"),
    ("w2_d", "Week 2 · decisions"),
    ("w2", "Week 2 · build"),
    ("w3_d", "Week 3 · decisions"),
    ("w3", "Week 3 · build"),
    ("pw4", "Pre-W4 refactor"),
    ("w4", "Week 4 · now"),
]
nodes = []
edges = []
main = []


def step(id, lane, col, label, sub, status="done"):
    t = {"done": "backend", "pending": "external"}[status]
    nodes.append(dict(id=id, lane=lane, col=col, type=t, label=label, sublabel=sub, tag=status, width=W))
    main.append(id)


def dec(id, lane, col, label, sub, date, to=None, elabel=None):
    nodes.append(dict(id=id, lane=lane, col=col, type="security", label=label, sublabel=sub, tag=date, width=W))
    if to:
        edges.append(dict(id="e_" + id, **{"from": id, "to": to}, variant="dashed", role="branch"))


# Project start
dec("d2", "start_d", 0, "ADR-2 Feature-sliced", "code grouped by feature", "Sep 23", "w1_rules")
dec("d1", "start_d", 1, "ADR-1 LangGraph", "visible, auditable flow", "Sep 23")
dec("d3", "start_d", 2, "ADR-3 MCP in repo", "one repo, one deploy", "Sep 23")
# W1
step("w1_rules", "w1", 0, "Folders + rules", "EU261 rules, tested")
step("w1_api", "w1", 1, "Call AI APIs directly", "OpenAI vs Anthropic")
step("w1_tools", "w1", 2, "Tools + deny-all gate", "stub blocks all actions")
step("w1_triage", "w1", 3, "/triage endpoint", "API + unit tests")
step("w1_stream", "w1", 4, "Streaming replies", "live updates (SSE)")
step("w1_reply", "w1", 5, "Checked replies", "validate, retry, backup")
dec("d4", "w1_d", 2, "ADR-4 EU261 tools", "real law, real money", "Sep 24", "w1_tools")
dec("d7", "w1_d", 4, "ADR-7 SSE", "one-way, plain HTTP", "Sep 26", "w1_stream")
dec("d5", "w1_d", 5, "ADR-5 Prompted JSON", "check reply, then fix", "Sep 26", "w1_reply")
dec("d6", "w1_d2", 5, "ADR-6 Two-layer retry", "retry, then switch model", "Sep 26", "w1_reply")
# W2
step("w2_loop", "w2", 0, "Agent loop", "rebuilt in LangGraph")
step("w2_mcp", "w2", 1, "MCP tool server", "4 tools exposed")
step("w2_amcp", "w2", 2, "Agent uses MCP", "tools called over MCP")
step("w2_mem", "w2", 3, "Agent memory", "short + long term")
step("w2_esc", "w2", 4, "Escalate / retry", "low confidence → human")
step("w2_gate", "w2", 5, "Human approval gate", "replaces deny-all stub")
dec("d8", "w2_d", 4, "ADR-8 Memory approval", "simple; replaced", "Sep 28", "w2_gate")
dec("d9", "w2_d", 5, "ADR-9 Approve once", "approve once, run once", "Sep 28", "w2_gate")
edges.append(dict(id="e_d8d9", **{"from": "d8", "to": "d9"}, label="replaced by", variant="dashed", role="branch"))
# W3
step("w3_pg", "w3", 0, "Postgres + pgvector", "durable data + vectors")
step("w3_rag", "w3", 1, "RAG search", "chunk, embed, retrieve")
step("w3_eval", "w3", 2, "Retrieval eval", "30 labelled questions")
step("w3_docker", "w3", 3, "Docker Compose", "one-command stack")
step("w3_guard", "w3", 4, "PII + injection", "redact; flag attacks")
step("w3_it", "w3", 5, "End-to-end test", "/triage over real stack")
dec("d10", "w3_d", 0, "ADR-10 pgvector", "one DB, one commit", "Oct 6", "w3_pg")
dec("d11", "w3_d", 1, "ADR-11 Chunking", "whole sections, cited", "Oct 7", "w3_rag")
dec("d12", "w3_d", 2, "ADR-12 Score floor", "best cut-off, no loss", "Oct 8", "w3_eval")
dec("d13", "w3_d", 3, "ADR-13 PII redaction", "hide personal data", "Oct 8", "w3_guard")
dec("d14", "w3_d", 4, "ADR-14 Injection", "a hit goes to human", "Oct 8", "w3_guard")
# Pre-W4
step("p1", "pw4", 0, "P-1 Wiring", "approval store injected")
step("p2", "pw4", 1, "P-2 Executors", "claims + payments saved")
step("p3", "pw4", 2, "P-3 Shared preamble", "one setup, two paths")
step("p4", "pw4", 3, "P-4 Docs fixed", "docs match the code")
# W4
step("w4_doc", "w4", 0, "Diagram + README", "design + trade-offs")
nodes.append(
    dict(
        id="here",
        lane="w4",
        col=1,
        type="frontend",
        label="YOU ARE HERE",
        sublabel="Week 4: 1 of 4 done",
        tag="now",
        width=W,
    )
)
main.append("here")
step("w4_otel", "w4", 2, "Tracing (OTel)", "span per AI/tool call", "pending")
step("w4_rego", "w4", 3, "Payout policy (Rego)", "block big auto-payouts", "pending")
step("w4_audit", "w4", 4, "Audit trail", "every call + decision", "pending")
nodes_col = {n["id"]: n["col"] for n in nodes}
# main edges
for a, b in zip(main, main[1:]):
    if nodes_col[a] > nodes_col[b]:
        continue
    edges.append(dict(id=f"m_{a}_{b}", **{"from": a, "to": b}, variant="emphasis"))
main = [m for m in main if m.startswith("w1_")]
cards = [
    dict(
        dot="amber",
        title="Current stage",
        items=[
            "Week 4 is under way: 1 of 4 tasks done (architecture diagram + README).",
            "Weeks 1-3 and the pre-W4 refactor (P-1 to P-4) are finished.",
            "Next (list order): tracing → payout policy → audit trail.",
        ],
    ),
    dict(
        dot="rose",
        title="Flagged gaps",
        items=[
            "tasks.md has no 'in progress' state; Week 4 is shown as current because it is partly done.",
            "tasks.md does not rank the 3 pending tasks; its list order is used. Priority lives on the Notion board.",
            "tasks.md carries no dates. Order follows the task list; decision dates come from the ADRs.",
            "tasks.md was last synced with Notion on 2026-09-24.",
            "Weeks 1-3 merge some related tasks into one box (e.g. stub + tool schemas).",
        ],
    ),
    dict(
        dot="violet",
        title="Decisions in one line (1-7)",
        items=[
            "ADR-1 LangGraph: explicit flow is easier to explain and audit than agents chatting.",
            "ADR-2 Feature-sliced: all claims-triage code sits together; shared plumbing stays generic.",
            "ADR-3 MCP in repo: shows the protocol without a second service to deploy.",
            "ADR-4 EU261 tools: a real, checkable law and real money beat invented ticket tools.",
            "ADR-5 Prompted JSON: ask for JSON, validate it, ask again on errors.",
            "ADR-6 Two-layer retry: SDK retries blips; a fallback model covers outages.",
            "ADR-7 SSE: the stream is one-way, so plain HTTP is enough.",
        ],
    ),
    dict(
        dot="violet",
        title="Decisions in one line (8-14)",
        items=[
            "ADR-8 In-memory approval: simplest first version; superseded by ADR-9.",
            "ADR-9 Approve once: the approval request is the action, run exactly once after a human says yes.",
            "ADR-10 pgvector: one database means one transaction for claim, approval, search data.",
            "ADR-11 Chunks + embeddings: cut at headings so every citation is a whole section.",
            "ADR-12 Score floor 0.35: highest cut-off that loses no correct answers.",
            "ADR-13 PII redaction: strip personal data at every boundary, one-way.",
            "ADR-14 Injection check: simple pattern checks; a hit goes to a human, nothing is lost.",
        ],
    ),
    dict(
        dot="cyan",
        title="Key terms · the problem",
        items=[
            "EU261: the EU flight-compensation rule; rules.py holds its tiers and exemptions → Folders + rules engine, ADR-4.",
            "Triage: reading a claim and deciding what happens next → Week 1 /triage endpoint.",
            "Escalation: handing a claim to a human instead of deciding → Escalate / retry, ADR-14.",
        ],
    ),
    dict(
        dot="emerald",
        title="Key terms · the agent",
        items=[
            "Agent: the AI that reads a claim and calls tools → Agent loop.",
            "LangGraph: library that lays the agent out as steps and arrows → ADR-1, Agent loop.",
            "Tool: an action the agent can call (search_kb, check_eligibility, log_claim, issue_payment) → ADR-4.",
            "MCP: standard way to offer tools to any AI client → ADR-3, MCP tool server.",
            "Structured output: a reply in a fixed, checkable shape → ADR-5.",
            "SSE: server pushes updates over plain HTTP → ADR-7.",
        ],
    ),
    dict(
        dot="orange",
        title="Key terms · safety",
        items=[
            "Approval gate: a state-changing action waits for a human yes → ADR-8, ADR-9.",
            "Exactly once: an approved action runs once, never twice → ADR-9, Executors.",
            "PII redaction: replaces emails, IBANs etc. with placeholders → ADR-13.",
            "Prompt injection: text that tries to give the AI new orders → ADR-14.",
        ],
    ),
    dict(
        dot="slate",
        title="Key terms · data and platform",
        items=[
            "RAG: look up policy text first, then answer with citations → RAG search.",
            "Embedding: numbers that capture a text's meaning → ADR-11.",
            "pgvector: Postgres add-on that stores embeddings → ADR-10.",
            "Relevance floor: minimum score for a search hit to count → ADR-12.",
            "Eval set: labelled questions that measure search quality → Retrieval eval.",
            "Docker Compose: starts the whole stack with one command → Docker Compose.",
            "Composition root: the one place that wires parts together → P-1 Wiring, ADR-2.",
        ],
    ),
    dict(
        dot="cyan",
        title="Key terms · coming in Week 4",
        items=[
            "OpenTelemetry: tracing, a span per AI or tool call → Tracing.",
            "OPA/Rego: policy code; rule is 'block auto-payout above €X' → Payout policy.",
            "Audit trail: a log of every tool call and decision → Audit trail.",
        ],
    ),
]
meta = dict(
    title="Ombuds Development Board · v1.0 · 2026-10-18",
    output="/tmp/development-overview.html",
    quality_profile="showcase",
    legend=dict(
        mode="all",
        entries=dict(
            backend=dict(label="Step · done"),
            external=dict(label="Step · pending"),
            security=dict(label="Decision (ADR) + date"),
            frontend=dict(label="You are here"),
        ),
    ),
)
d = dict(
    schema_version=2,
    diagram_type="workflow",
    meta=meta,
    lanes=[dict(id=i, label=l) for i, l in lanes],
    mainPath=main,
    nodes=nodes,
    edges=edges,
    cards=cards,
)
json.dump(d, open(sys.argv[1], "w"), indent=1, ensure_ascii=False)
