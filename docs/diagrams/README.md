# Diagrams

This folder is the one home for diagrams. **Every diagram has one page, `<slug>.md`, built from [`_template.md`](_template.md)**: title, version, date, pinned commit, the diagram, what it shows, a child and an interviewer explanation, and how to regenerate it. Other docs (ADRs, `architecture.md`, the root README) link to that page instead of repeating the diagram.

| Path | What it holds |
|---|---|
| `<slug>.md` | The diagram page (the thing to read and link to). |
| `archify/` | For archify diagrams: `<slug>.json` (source, pinned to a commit), `<slug>.html` (interactive) and `<slug>.png` (embedded in the page). |
| `src/` | Scripts: `render_archify.py` rebuilds an archify `.html` and `.png`; `development_board_gen.py` generates board v1's JSON. |

## Versioning

Each diagram is `MAJOR.MINOR` with a date, shown in the page header and in the diagram's own title (`meta.title` for archify, the front-matter `title:` for Mermaid). Bump MINOR for a redraw or accuracy fix, MAJOR when the system it shows changes shape, and add a line to the page's change log. The pinned commit is the code revision the diagram was last checked against.

## Diagram index

| Diagram | Ver | Date | Tool | Decisions |
|---|---|---|---|---|
| [Ombuds Claims Triage](architecture.md) | 1.0 | 2026-10-18 | archify | ADR-0001, 0002, 0009 |
| [Triage and Approval Flow](triage-approval-flow.md) | 1.0 | 2026-10-18 | archify | ADR-0009, 0014 |
| [Guardrails and Tool Scoping Pipeline](guardrails-pipeline.md) | 1.0 | 2026-10-18 | archify | ADR-0013, 0014 |
| [RAG Ingest, Retrieval and Evals](rag-evals-pipeline.md) | 1.0 | 2026-10-18 | archify | ADR-0010, 0011, 0012 |
| [MCP Process Boundary](mcp-boundary.md) | 1.0 | 2026-10-18 | archify | ADR-0003 |
| [Ombuds Development Board](development-overview.md) | 1.0 | 2026-10-18 | archify | all |
| [Ombuds Development Board v2](development-overview-v2.md) | 1.0 | 2026-10-18 | archify | all |

Mermaid diagrams, still inline in the doc they explain until they get their own pages:

| Diagram | Tool | Where |
|---|---|---|
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

Their plain-language explanations are in [explained.md](explained.md).

## Which tool

- **Mermaid**: small diagrams that sit beside prose (state machines, flowcharts, ER). GitHub renders them, no binaries.
- **archify**: large multi-actor diagrams that need layout control.

## Regenerate an archify diagram

From the repo root: `python docs/diagrams/src/render_archify.py <slug>` (needs node, the archify skill, google-chrome and Pillow). It runs `archify finalize` and rewrites the `.html` and `.png`. archify writes scratch runs to `.archify/` at the repo root. It is gitignored; delete it freely.
