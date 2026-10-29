import json
import sys

W = 146
lanes = [
    ("start_d", "Project start · decisions"),
    ("w1_d", "Foundations · decisions"),
    ("w1_d2", "Foundations · decisions (2)"),
    ("w1", "Foundations · build"),
    ("w2_d", "Agent loop · decisions"),
    ("w2", "Agent loop · build"),
    ("w3_d", "Data layer · decisions"),
    ("w3", "Data layer · build"),
    ("pw4", "Durable approvals · refactor"),
    ("w4_d", "Governance · decisions"),
    ("w4", "Governance · build"),
    ("w5_d", "Governance holes · decisions"),
    ("w5", "Governance holes · build"),
    ("w6_d", "Guards and evals · decisions"),
    ("w6", "Guards and evals · build"),
    ("w7", "Provider composition · now"),
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
# Foundations
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
# Agent loop
step("w2_loop", "w2", 0, "Agent loop", "rebuilt in LangGraph")
step("w2_mcp", "w2", 1, "MCP tool server", "4 tools exposed")
step("w2_amcp", "w2", 2, "Agent uses MCP", "tools called over MCP")
step("w2_mem", "w2", 3, "Agent memory", "short + long term")
step("w2_esc", "w2", 4, "Escalate / retry", "low confidence → human")
step("w2_gate", "w2", 5, "Human approval gate", "replaces deny-all stub")
dec("d8", "w2_d", 4, "ADR-8 Memory approval", "simple; replaced", "Sep 28")
dec("d9", "w2_d", 5, "ADR-9 Approve once", "approve once, run once", "Sep 28", "w2_gate")
edges.append(dict(id="e_d8d9", **{"from": "d8", "to": "d9"}, label="replaced by", variant="dashed", role="branch"))
# Data layer
step("w3_pg", "w3", 0, "Postgres + pgvector", "durable data + vectors")
step("w3_rag", "w3", 1, "RAG search", "chunk, embed, retrieve")
step("w3_eval", "w3", 2, "Retrieval eval", "30 labelled questions")
step("w3_docker", "w3", 3, "Docker Compose", "one-command stack")
step("w3_guard", "w3", 4, "PII + injection", "redact; flag attacks")
step("w3_it", "w3", 5, "End-to-end test", "/triage over real stack")
dec("d10", "w3_d", 0, "ADR-10 pgvector", "one DB, one commit", "Oct 6", "w3_pg")
dec("d11", "w3_d", 1, "ADR-11 Chunking", "whole sections, cited", "Oct 7", "w3_rag")
dec("d12", "w3_d", 2, "ADR-12 Score floor", "best cut-off, no loss", "Oct 8", "w3_eval")
dec("d13", "w3_d", 4, "ADR-13 PII redaction", "hide personal data", "Oct 8", "w3_guard")
dec("d14", "w3_d", 5, "ADR-14 Injection", "a hit goes to human", "Oct 8", "w3_guard")
# Durable approvals
step("p1", "pw4", 0, "P-1 Wiring", "approval store injected")
step("p2", "pw4", 1, "P-2 Executors", "claims + payments saved")
step("p3", "pw4", 2, "P-3 Shared preamble", "one setup, two paths")
step("p4", "pw4", 3, "P-4 Docs fixed", "docs match the code")
# Governance
step("w4_otel", "w4", 0, "Tracing (OTel)", "span per AI/tool call")
step("w4_rego", "w4", 1, "Payout policy (Rego)", "block big auto-payouts")
step("w4_audit", "w4", 2, "Audit trail", "every call + decision")
step("w4_doc", "w4", 3, "Diagram + README", "design + trade-offs")
dec("d17", "w4_d", 0, "ADR-17 Tracing", "spans at existing seams", "Oct 18", "w4_otel")
dec("d15", "w4_d", 1, "ADR-15 OPA sidecar", "policy outside the code", "Oct 18", "w4_rego")
dec("d16", "w4_d", 2, "ADR-16 Audit log", "append-only, in Postgres", "Oct 18", "w4_audit")
# Governance holes
step("w5_net", "w5", 0, "Ports locked down", "localhost only + healthcheck")
step("w5_rec", "w5", 1, "Recoverable approvals", "retry route, no stuck requests")
step("w5_auth", "w5", 2, "API authentication", "two bearer tokens, fail closed")
step("w5_db", "w5", 3, "No default DB password", "set in .env or refuse")
step("w5_lint", "w5", 4, "Lint green again", "two long lines fixed")
step("w5_docs", "w5", 5, "Docs match the code", "README, diagrams, architecture")
dec("d19", "w5_d", 2, "ADR-19 Bearer tokens", "one per role, per router", "Oct 22", "w5_auth")
# Guards and evals
step("w6_ci", "w6", 0, "CI + secret scans", "lint, tests, gitleaks")
step("w6_audit", "w6", 1, "Audit completed", "refusals + injection recorded")
step("w6_eval", "w6", 2, "Agent eval", "real agent on 15-25 claims")
step("w6_cfg", "w6", 3, "MCP env + 4096 tokens", "child inherits config")
step("w6_cap", "w6", 4, "Spend-cap tests", "no failover, one ledger")
step("w6_tidy", "w6", 5, "Tidy + final checks", "dead stubs gone, limits set")
dec("d18", "w6_d", 4, "ADR-18 Spend cap", "budget in a provider wrapper", "Oct 18", "w6_cap")
# Provider composition
nodes.append(
    dict(
        id="here",
        lane="w7",
        col=0,
        type="frontend",
        label="YOU ARE HERE",
        sublabel="Stage 7: 0 of 1 done",
        tag="now",
        width=W,
    )
)
main.append("here")
step("w7_roots", "w7", 1, "Providers in the roots", "build once, inject", "pending")
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
            "Sections 1 to 6 and the durable-approvals refactor are finished; Provider composition has one task left.",
            "Next: build the LLM provider and spend budget once in the composition roots and inject them.",
            "Open items without a section are in the Later list of tasks.md.",
        ],
    ),
    dict(
        dot="rose",
        title="Flagged gaps",
        items=[
            "tasks.md has no 'in progress' state; Provider composition is shown as current because it is the first with open work.",
            "tasks.md carries no dates. Order follows the task list; decision dates come from the ADRs.",
            "The repo is the source of truth; the Notion board is no longer synced.",
            "The Foundations, Agent loop and Data layer sections merge some related tasks into one box (e.g. stub + tool schemas), and the last two sections group small tasks.",
            "ADR-18 (spend cap) was not a board task; it is shown beside the Guards and evals tests that pin it.",
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
        dot="violet",
        title="Decisions in one line (15-19)",
        items=[
            "ADR-15 OPA sidecar: the payout rule lives in a reviewable policy file and fails closed.",
            "ADR-16 Audit log: an append-only Postgres table written at the existing seams.",
            "ADR-17 Tracing: OpenTelemetry spans at the same seams, ids and counts only.",
            "ADR-18 Spend cap: a process-wide budget in a provider wrapper; a spent budget refuses the turn.",
            "ADR-19 Bearer tokens: one static token per role, attached to the routers, fail closed.",
        ],
    ),
    dict(
        dot="cyan",
        title="Key terms · the problem",
        items=[
            "EU261: the EU flight-compensation rule; rules.py holds its tiers and exemptions → Folders + rules engine, ADR-4.",
            "Triage: reading a claim and deciding what happens next → Foundations /triage endpoint.",
            "Escalation: handing a claim to a human instead of deciding → Escalate / retry, ADR-14.",
        ],
    ),
    dict(
        dot="emerald",
        title="Key terms · the agent",
        items=[
            "Agent: the AI that reads a claim and calls tools → Agent loop.",
            "LangGraph: library that lays the agent out as steps and arrows → ADR-1, Agent loop.",
            "Tool: an action the agent can call (search_kb, check_eligibility, log_claim) → ADR-4.",
            "MCP: standard way to offer tools to any AI client → ADR-3, MCP tool server.",
            "Structured output: a reply in a fixed, checkable shape → ADR-5.",
            "SSE: server pushes updates over plain HTTP → ADR-7.",
            "Agent eval: the real agent run over labelled claims, scored but never failing CI → Agent eval.",
        ],
    ),
    dict(
        dot="orange",
        title="Key terms · safety and governance",
        items=[
            "Approval gate: a state-changing action waits for a human yes → ADR-8, ADR-9.",
            "Exactly once: an approved action runs once, never twice → ADR-9, Executors.",
            "PII redaction: replaces emails, IBANs etc. with placeholders → ADR-13.",
            "Prompt injection: text that tries to give the AI new orders → ADR-14.",
            "OPA/Rego: policy code; the rule is 'block auto-payout above the limit' → ADR-15.",
            "Audit trail: an append-only log of every tool call and decision → ADR-16.",
            "OpenTelemetry: tracing, a span per AI or tool call → ADR-17.",
            "Bearer token: a secret sent with each request to prove the caller's role → ADR-19.",
            "Spend cap: a budget that stops model calls once spent → ADR-18.",
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
            "Composition root: the one place that wires parts together → P-1 Wiring, ADR-2, Providers in the roots.",
            "CI and gitleaks: automatic lint, tests and secret scanning on every change → CI + secret scans.",
        ],
    ),
]
meta = dict(
    title="Ombuds Development Board · v2.1 · 2026-10-29",
    output="docs/diagrams/development-overview/development-overview.html",
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
with open(sys.argv[1], "w") as out:
    json.dump(d, out, indent=1, ensure_ascii=False)
    out.write("\n")
