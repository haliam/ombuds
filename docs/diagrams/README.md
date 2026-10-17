# Diagrams

This folder is the one home for diagram sources and outputs.

| Path | What it holds |
|---|---|
| `archify/` | Showcase diagrams made with the archify skill: `<name>.json` (source, pinned to a commit), `<name>.html` (interactive) and `<name>.png` (embedded in docs). |
| `src/` | Scripts that generate an archify JSON (e.g. `development_board_gen.py`). |

Mermaid diagrams are not stored here. They live inline in the doc they explain (ADRs, `docs/architecture.md`).

## Diagram index

| Diagram | Tool | Where |
|---|---|---|
| Component architecture | archify | [`architecture.md`](../architecture.md) (`archify/architecture.*`) |
| Triage and approval sequence | archify | [`architecture.md`](../architecture.md#triage-and-approval-flow) (`archify/triage-approval-flow.*`) |
| Guardrails and tool scoping | archify | [`architecture.md`](../architecture.md#guardrails-and-tool-scoping) (`archify/guardrails-pipeline.*`) |
| RAG ingest, retrieval and evals | archify | [`architecture.md`](../architecture.md#rag-and-evals) (`archify/rag-evals-pipeline.*`) |
| MCP process boundary | archify | [`architecture.md`](../architecture.md#mcp-process-boundary) (`archify/mcp-boundary.*`) |
| Development history boards | archify | [`architecture.md`](../architecture.md#development-history) (`archify/development-overview*.*`) |
| Postgres data model | Mermaid | [`architecture.md`](../architecture.md#data-model) |
| Layering and composition roots | Mermaid | [`architecture.md`](../architecture.md#layering) |
| Approval lifecycle | Mermaid | [ADR-0009](../decisions/0009-approval-request-is-the-pending-action.md#lifecycle-of-an-approval-request) |
| LangGraph triage loop | Mermaid | [ADR-0005](../decisions/0005-prompted-json-with-repair-over-native-structured-output.md#the-triage-graph-end-to-end) |
| Provider fallback | Mermaid | [ADR-0006](../decisions/0006-two-layer-resilience-over-a-retry-library.md#how-a-failure-travels) |
| SSE event order | Mermaid | [ADR-0007](../decisions/0007-sse-over-websockets-for-triage-streaming.md#event-order-of-one-streamed-triage) |
| Docker Compose startup | Mermaid | [`architecture.md`](../architecture.md#deployment) |
| Memory flow | Mermaid | [`architecture.md`](../architecture.md#memory) |
| Prompt versioning | Mermaid | [`architecture.md`](../architecture.md#prompt-versioning) |
| Injection detection internals | Mermaid | [ADR-0014](../decisions/0014-heuristic-injection-detection-escalates.md#inside-detect) |

## Which tool

- **Mermaid**: small diagrams that sit beside prose (state machines, flowcharts, ER). GitHub renders them, no binaries.
- **archify**: large multi-actor diagrams that need layout control.

## Regenerate an archify diagram

From the repo root:

```bash
node ~/.claude/skills/archify/bin/archify.mjs finalize <type> docs/diagrams/archify/<name>.json /tmp/<name>.html --repo-root . --quality showcase
```

archify writes scratch runs to `.archify/` at the repo root. It is gitignored; delete it freely.
