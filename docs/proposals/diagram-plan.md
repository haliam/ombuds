# Plan: archify diagrams for the hard-to-grasp parts of ombuds

## Context
`docs/diagrams/` already has `architecture` (components), `triage-approval-flow` (sequence) and two `development-overview` timelines (each as .json/.html/.png, built with the archify skill). The dynamic mechanisms that the glossary and ADRs explain only in prose are not drawn: loops, turns, state machines, RAG, evals, memory. Goal: add a small, prioritized set of diagrams, wire them into the docs, and draw unbuilt Week-4 parts (policy engine/Rego, tracing, audit) as dashed "planned" boxes.

## Diagram candidates and tool per topic (priority order)
Tool rule: **Mermaid** (text, renders natively on GitHub, no binaries) for diagrams that sit beside prose in ADRs/glossary; **archify** (rich layout, HTML+PNG) for the large multi-actor showcase diagrams; **generated** where the code can emit the diagram itself.

| # | Diagram | Tool | Mermaid type / archify type | Covers (glossary / ADR) | Source of truth |
|---|---|---|---|---|---|
| 1 | Approval lifecycle | **Mermaid** | `stateDiagram-v2` | exactly-once, compare-and-set, executor, ADR-0008/0009 | `platform/guardrails/approval_gate.py`, `executing_store.py`, `infrastructure/repositories.py` |
| 2 | LangGraph triage loop | **Mermaid** (hand-drawn with caps and escalation reasons) + `graph.get_graph().draw_mermaid()` as a drift cross-check | `flowchart` | LangGraph, repair loop, escalation, ADR-0001/0005 | `agent/graph.py`, `state.py`, `nodes/escalate_retry.py` |
| 3 | Guardrails + tool scoping pipeline | **archify** | data-flow with trust boundaries | PII, injection, NFKC, ADR-0013/0014 | `triage_use_case.py`, `injection_detection.py`, `pii_filter.py`, `guarded_dispatcher.py`, `tools/__init__.py` |
| 4 | Postgres data model | **Mermaid** (tables checked against the migrations, optionally generated from the live schema) | `erDiagram` | ADR-0009 | `infrastructure/migrations/0001_init.sql`, `0002_payments.sql` |
| 5 | RAG ingest + retrieval with eval floor sweep | **archify** | two-lane data-flow | chunking, embedding, cosine, relevance floor, evals, ADR-0010/11/12 | `rag/*`, `vector_store.py`, `evals/run_evals.py`, `retrieval_metrics.py` |
| 6 | Layering + composition roots | **Mermaid** (optionally cross-checked by an `import-linter` graph) | `flowchart` with subgraphs | ADR-0002/0003, lifespan, ExitStack | `api_app.py`, `runtime.py`, `platform/mcp/server.py` |
| 7 | Provider retry/fallback + streaming | **Mermaid** | `flowchart` (retry layers) + `sequenceDiagram` (stream events) | ADR-0006/0007, JSON buffering, SSE | `providers/fallback.py`, `tool_loop.py`, `streaming.py` |
| 8 | MCP process boundary | **archify** | architecture with process boundaries | MCP, BlockingPortal, stdio | `mcp/server.py`, `tool_bindings.py`, `mcp/client.py` |

Result: 5 Mermaid (#1, #2, #4, #6, #7), 3 archify (#3, #5, #8). Mermaid blocks go inline in the ADR/glossary/architecture doc they explain; archify outputs go in `docs/diagrams/` as before.

Fold into the above rather than separate diagrams: guarded-tools submit→execute invariants (into #1), memory (short-term facts from `check_eligibility`, long-term load/consolidate; into #2 as a side lane), prompt versioning v1–v4 (small panel on #2).

Findings to represent honestly (not hide):
- Cross-run long-term memory is not wired into the HTTP API (`routes.py` omits `claimant_id`); only the library path uses it. Mark it as such.
- `evals/datasets/airline_claims.jsonl` is empty: no end-to-end agent/prompt eval yet. Draw as planned.
- Policy engine, OPA/Rego, tracing, metrics, audit are stubs: dashed "not built".
- No automated import-layering check exists; ADR-0002 is convention only.

## Step 0: consolidate diagram locations (do first, own commit)
Today diagrams live in two places: `docs/diagrams/` (committed: json/html/png) and `.archify/` at the repo root (gitignored archify scratch: 3 run folders, `candidate.json`, finalize summaries, and two `gen.py` scripts that generated the development-overview boards). Make `docs/diagrams/` the single home:
- Layout: `docs/diagrams/archify/` (existing json/html/png moved with `git mv`, so history is kept), `docs/diagrams/src/` (the useful `gen.py` generator scripts rescued from `.archify/`), and `docs/diagrams/README.md` (what lives where, the tool rule Mermaid vs archify, regeneration commands). Mermaid diagrams stay inline in the docs that explain them.
- Delete the stale `.archify/` run folders; keep the `.archify/` line in `.gitignore` so future archify scratch never gets committed.
- Update every reference to the old paths: `README.md` (lines ~25, 39 image embeds), `docs/architecture.md` (image embeds, json/html links, the regeneration command `docs/diagrams/architecture.json`), `docs/progress/glossary.md` (archify term, line ~106), `docs/progress/task_summaries.md` (~529-545), `docs/build_and_explain.md`. Grep for `diagrams/` afterwards; no stale link may remain.
- The `commit` pin in each json is unaffected; regeneration command changes to the new `docs/diagrams/archify/<name>.json` path.
- Verify: `grep -rn "diagrams/" --include=*.md .` resolves to existing files, the README images render, `git status` shows renames (not delete+add), pre-commit passes.

## Implementation steps
1. For Mermaid diagrams: write the fenced ```mermaid block directly in the target doc (ADR-0009 for #1, ADR-0001/0005 for #2, architecture.md for #4/#6/#7), and link it from the glossary entry. For archify diagrams: load the `archify` skill; follow its authoring flow (JSON source → finalize → HTML + PNG), reusing the style, commit-pin and regeneration command already used in `docs/architecture.md`.
2. Create diagrams #1–#3 first (highest value), then #4–#8. Archify ones go to `docs/diagrams/archify/<name>.{json,html,png}` (after Step 0). Pin each to the current commit and cite source file:line, as the existing ones do.
3. Embed the PNGs in the relevant docs: `docs/architecture.md` (new sections), and link them from matching ADRs (0001, 0005, 0006, 0009, 0013) and from `docs/progress/glossary.md` entries. Keep README to the existing two images plus a link.
4. Mermaid avoids the 500 KB `check-added-large-files` hook entirely. For the three archify diagrams (~850 KB HTML each), check how existing HTMLs are handled (excluded vs committed) and follow that; do not bypass the hook.
5. Update `docs/progress/task_summaries.md` / `tasks.md`; commit per diagram batch (user's preference: one commit per task, user pushes).

## Scope question for execution
Eight diagrams is a lot; per the "one chat per task" preference, suggest doing #1–#3 in this task and the rest in later chats.

## Verification
- archify validation passes for each JSON (its `finalize`/validate command) and PNGs render legibly at desktop width.
- Each diagram's states/edges are spot-checked against the cited source lines (e.g. `MAX_TOOL_TURNS=8`, `MAX_REPAIR_ATTEMPTS=2`, floor 0.35, status set pending/approved/denied/executed).
- Mermaid blocks render on GitHub preview/VS Code; #2 matches `draw_mermaid()` output node-for-node.
- Markdown image links resolve; `make lint` still passes; pre-commit large-file hook passes.
