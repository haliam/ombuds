# Diagrams

This folder is the one home for diagrams. **Every diagram has its own folder with one page, `<slug>/README.md`, built from [`_template.md`](_template.md)**: title, version, date, pinned commit, the diagram, what it shows, a child and an interviewer explanation, and how to regenerate it. Other docs (ADRs, `architecture.md`, the root README) link to that page instead of repeating the diagram.

| Path | What it holds |
|---|---|
| `<slug>/README.md` | The diagram page (the thing to read and link to). Every diagram has a folder with one. |
| `<slug>/<slug>.json`, `.html`, `.png` | Only for archify diagrams: the source (pinned to a commit), the interactive page and the image embedded in the page. Mermaid diagrams have just the `README.md`, because the diagram is inside it. |
| `_template.md` | Template for a new diagram's `README.md`. |
| `render_archify.py` | Rebuilds an archify diagram's `.html` and `.png` from its JSON. |
| `development_board_gen.py` | Generates development board v1's JSON. |

## Versioning

Each diagram is `MAJOR.MINOR` with a date, shown in the page header and in the diagram's own title (`meta.title` for archify, the front-matter `title:` for Mermaid). Bump MINOR for a redraw or accuracy fix, MAJOR when the system it shows changes shape, and add a line to the page's change log. The pinned commit is the code revision the diagram was last checked against.

## Diagram index

| Diagram | Ver | Date | Tool | Decisions |
|---|---|---|---|---|
| [Ombuds Claims Triage](architecture/README.md) | 1.0 | 2026-10-18 | archify | ADR-0001, 0002, 0009 |
| [Triage and Approval Flow](triage-approval-flow/README.md) | 1.0 | 2026-10-18 | archify | ADR-0009, 0014 |
| [Guardrails and Tool Scoping Pipeline](guardrails-pipeline/README.md) | 1.0 | 2026-10-18 | archify | ADR-0013, 0014 |
| [RAG Ingest, Retrieval and Evals](rag-evals-pipeline/README.md) | 1.0 | 2026-10-18 | archify | ADR-0010, 0011, 0012 |
| [MCP Process Boundary](mcp-boundary/README.md) | 1.0 | 2026-10-18 | archify | ADR-0003 |
| [Claim Artifact Map](artifact-map/README.md) | 1.0 | 2026-10-19 | archify | ADR-0003, 0009, 0010, 0015, 0016, 0017 |
| [Claim Run Sequence](claim-sequence/README.md) | 1.0 | 2026-10-19 | archify | ADR-0009, 0012, 0014, 0015 |
| [Ombuds Development Board](development-overview/README.md) | 1.0 | 2026-10-18 | archify | all |
| [Ombuds Development Board v2](development-overview-v2/README.md) | 1.0 | 2026-10-18 | archify | all |
| [Postgres Data Model](data-model/README.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0009, 0010 |
| [Layering and Composition Roots](layering/README.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0002, 0003 |
| [Approval Request Lifecycle](approval-lifecycle/README.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0009 |
| [LangGraph Triage Loop](triage-graph/README.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0001, 0005 |
| [Provider Retry and Fallback](provider-fallback/README.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0006, 0007 |
| [SSE Event Order](sse-event-order/README.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0007 |
| [Docker Compose Startup](compose-startup/README.md) | 1.0 | 2026-10-18 | Mermaid | none |
| [Memory Flow](memory-flow/README.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0009 |
| [Prompt Versioning](prompt-versioning/README.md) | 1.0 | 2026-10-18 | Mermaid | none |
| [Injection Detection Internals](injection-detection/README.md) | 1.0 | 2026-10-18 | Mermaid | ADR-0014 |

## Which tool

- **Mermaid**: small diagrams (state machines, flowcharts, ER, short sequences). The diagram lives in its page's ```mermaid block, with front-matter `title:`; GitHub renders it, no binaries.
- **archify**: large multi-actor diagrams that need layout control.

## Regenerate an archify diagram

From the repo root: `python docs/diagrams/render_archify.py <slug>` (needs node, the archify skill, google-chrome and Pillow). It runs `archify finalize` and rewrites the `.html` and `.png`. archify writes scratch runs to `.archify/` at the repo root. It is gitignored; delete it freely.
