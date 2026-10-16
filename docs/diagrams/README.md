# Diagrams

This folder is the one home for diagram sources and outputs.

| Path | What it holds |
|---|---|
| `archify/` | Showcase diagrams made with the archify skill: `<name>.json` (source, pinned to a commit), `<name>.html` (interactive) and `<name>.png` (embedded in docs). |
| `src/` | Scripts that generate an archify JSON (e.g. `development_board_gen.py`). |

Mermaid diagrams are not stored here. They live inline in the doc they explain (ADRs, `docs/architecture.md`).

## Which tool

- **Mermaid**: small diagrams that sit beside prose (state machines, flowcharts, ER). GitHub renders them, no binaries.
- **archify**: large multi-actor diagrams that need layout control.

## Regenerate an archify diagram

From the repo root:

```bash
node ~/.claude/skills/archify/bin/archify.mjs finalize <type> docs/diagrams/archify/<name>.json /tmp/<name>.html --repo-root . --quality showcase
```

archify writes scratch runs to `.archify/` at the repo root. It is gitignored; delete it freely.
