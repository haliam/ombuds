# Diagrams

This folder is the one home for diagrams. **Every diagram has one page, `<slug>.md`, built from [`_template.md`](_template.md)**: title, version, date, pinned commit, the diagram, what it shows, a child and an interviewer explanation, and how to regenerate it. Other docs (ADRs, `architecture.md`, the root README) link to that page instead of repeating the diagram.

| Path | What it holds |
|---|---|
| `<slug>.md` | The diagram page (the thing to read and link to). Every diagram has one. |
| `<slug>/` | Only for archify diagrams: `<slug>.json` (source, pinned to a commit), `<slug>.html` (interactive) and `<slug>.png` (embedded in the page). Mermaid diagrams have no folder, because the diagram is in the page. |
| `render_archify.py` | Rebuilds an archify diagram's `.html` and `.png` from its JSON. |
| `development_board_gen.py` | Generates development board v1's JSON. |

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
| [Postgres Data Model](data-model.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0009, 0010 |
| [Layering and Composition Roots](layering.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0002, 0003 |
| [Approval Request Lifecycle](approval-lifecycle.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0009 |
| [LangGraph Triage Loop](triage-graph.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0001, 0005 |
| [Provider Retry and Fallback](provider-fallback.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0006, 0007 |
| [SSE Event Order](sse-event-order.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0007 |
| [Docker Compose Startup](compose-startup.md) | 1.0 | 2026-10-18 | Mermaid | none |
| [Memory Flow](memory-flow.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0009 |
| [Prompt Versioning](prompt-versioning.md) | 1.0 | 2026-10-18 | Mermaid | none |
| [Injection Detection Internals](injection-detection.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0014 |

## Which tool

- **Mermaid**: small diagrams (state machines, flowcharts, ER, short sequences). The diagram lives in its page's ```mermaid block, with front-matter `title:`; GitHub renders it, no binaries.
- **archify**: large multi-actor diagrams that need layout control.

## Regenerate an archify diagram

From the repo root: `python docs/diagrams/render_archify.py <slug>` (needs node, the archify skill, google-chrome and Pillow). It runs `archify finalize` and rewrites the `.html` and `.png`. archify writes scratch runs to `.archify/` at the repo root. It is gitignored; delete it freely.
