---
name: add-diagram
description: Add or update a diagram in the ombuds repo with the project's fixed structure (folder + page from the template, version, index row, ADR link, child and interviewer explanations). Use whenever asked to draw, add, redraw or update a diagram.
argument-hint: "<what to draw> [--update <slug>]"
---

# Add or update an ombuds diagram

Every diagram is built the same way. The structure rules live in `docs/code-style.md` ("Diagrams") and `docs/diagrams/README.md` (index, versioning, regenerate); the page layout is `docs/diagrams/_template.md`. Read those first, don't restate them here. This skill adds the working rules around them.

## 1. Pick the tool
- **Mermaid**: small diagrams (state, flowchart, ER, short sequence) that sit beside prose. Lives in the page's ```mermaid block with a front-matter `title: <Title> · vX.Y · YYYY-MM-DD`.
- **archify**: large multi-actor diagrams that need layout control. Load the `archify` skill, write `<slug>/<slug>.json`, then `uv run --with pillow python docs/diagrams/render_archify.py <slug>`.
- Don't draw numeric charts or dashboards.

## 2. Source facts, don't guess
- Take every claim from `docs/architecture.md`, the ADRs (Decision and Consequences) and the code paths you cite under **Source** in the page header.
- Copy numbers from those docs (8 turns, 2 repairs, 0.35 floor, 1536 dims, 30 eval questions, 400 EUR payout limit); don't re-derive them.
- Draw unbuilt parts as dashed "not built" boxes, never as if they work. Known gaps to check before claiming otherwise: long-term memory not wired to the HTTP API, no end-to-end agent eval, no import-linter layering check. Verify each against the current code, since gaps close over time.

## 3. Build the page (`docs/diagrams/<slug>/README.md`)
Copy `_template.md`, then fill every section. Sections are not optional:
- Header: title, version `1.0` for new, date, tool, type, pinned commit (`git rev-parse --short HEAD`), decisions, source paths.
- **What it shows**: one or two sentences.
- **Like I'm 5**: ~70-100 words, one everyday analogy, short sentences, no acronyms, no code names.
- **For an interviewer**: ~130-170 words, plain text: the problem, the design choice and why, the trade-off, and an honest "not built yet" gap. Under one printed page.
- **Likely follow-up**: one question, one-line answer.
- **Regenerate** and **Change log**.
- Check word counts with `wc -w` on each text. These ranges match the existing pages; stay inside them.
- `development-overview` is a two-board page and is exempt from the single-header template; don't copy its shape.

## 4. Wire it in (same commit)
- Add a row to the index table in `docs/diagrams/README.md` (title, version, date, tool, decisions).
- Add `Diagram: [Title vX.Y](../diagrams/<slug>/README.md)` to the ADR it illustrates (and `architecture.md` if relevant). Link, never paste the diagram.
- Don't touch `docs/proposals/diagram-plan.md`; it is history.

## 5. Updating an existing diagram (`--update <slug>`)
Bump MINOR for a redraw or accuracy fix, MAJOR when the system's shape changed. Update the version and date in the page header, the diagram's own title, the index row and the change log. Re-pin the commit. Regenerate archify output.

## 6. Verify
- Every relative link and `Diagram:` link resolves to an existing file.
- Mermaid renders (valid syntax); archify `finalize` passes and the PNG is legible.
- Each "not built" claim still matches the code.
- Pre-commit passes (the 500 KB large-file hook applies; don't bypass it).

## 7. Commit
One commit per diagram, per the user's preference. Don't push.
