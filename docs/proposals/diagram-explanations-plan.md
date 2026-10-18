# Plan: plain-text explanations for every diagram (child + interviewer)

**Status: done, then superseded (2026-10-18).** `explained.md` was split so each explanation sits on its diagram's own page (`docs/diagrams/<slug>.md`) and the file was deleted. The text below is the original plan.

## Context
The repo now has 16 content diagrams (the earlier diagram plan is done and pushed on `add_diagrams`). They show how the system works but need a plain-language layer: one version a child could follow and one a candidate could say out loud in an interview for the AI/Agentic Engineer role this capstone prepares for. Decisions from the user: one new doc, all 16 content diagrams (not the two development-history boards), about 150-250 words per text, English, and each interviewer text ends with a likely follow-up question and honest gaps.

## Deliverable
New file `docs/diagrams/explained.md`, linked from `docs/diagrams/README.md` (index) and the root `README.md` ("More diagrams" line). One section per diagram, always in this shape:

```
## <Diagram name>
Diagram: <link to where it lives>

**Like I'm 5** (~120-150 words): one everyday analogy, no jargon, no code names.
**For an interviewer** (~200-250 words): the problem, the design choice and why, trade-offs, what is NOT built (honest gap).
**Likely follow-up:** one question, one-line answer.
```
Plain text only (no nested diagrams, no tables inside sections). Each section's two texts stay under one printed page.

## Diagrams and the angle for each (16)
| # | Diagram (link target) | Child analogy idea | Interviewer angle / honest gap |
|---|---|---|---|
| 1 | Component architecture (`architecture.md`) | a post office with a guard and a manager | layered design, composition roots; Week 4 pieces are stubs |
| 2 | Triage + approval sequence | filling a form, a clerk checks it, a boss signs later | nothing changes state until approval (ADR-0009) |
| 3 | Guardrails + tool scoping | a mailroom that checks and blacks out private bits | defence in depth, model authority ends at rules engine; tool results unfiltered; heuristic detection |
| 4 | RAG + evals | looking things up in a library with a "good enough" score | chunking, cosine, 0.35 floor chosen by eval sweep; no end-to-end agent eval yet |
| 5 | MCP process boundary | a helper in another room passing notes through a slot | stdio subprocess, sync-to-async bridge; HTTP API does not use MCP |
| 6 | Data model (ER) | filing cabinets with labelled folders | FK only on payments; logical link via payload; pgvector in same DB (ADR-0010) |
| 7 | Layering + composition roots | LEGO with a rule about which bricks go on top | feature-sliced (ADR-0002); rule is convention, no import-linter |
| 8 | Approval lifecycle | a permission slip that can only be used once | compare-and-set, exactly-once, crash recovery (ADR-0009) |
| 9 | LangGraph triage loop | a helper who tries, checks, and asks a grown-up if stuck | caps (8 turns, 2 repairs), escalation not exception (ADR-0001/0005) |
| 10 | Provider fallback | a spare bike when the first has a flat tyre | two-layer resilience, no mid-stream failover (ADR-0006) |
| 11 | SSE event order | a friend telling you each step as it happens | SSE vs WebSockets, model text never streamed unverified (ADR-0007) |
| 12 | Compose startup | building a house: foundation, then furniture, then open the door | healthchecks, one-shot migrate-ingest, idempotence |
| 13 | Memory | a notebook of facts about each visitor | short vs long term, rules-derived only, not wired into the HTTP API |
| 14 | Prompt versioning | numbered recipe cards, never erase old ones | bump-don't-edit, eval gate is policy only (dataset empty) |
| 15 | Injection detection internals | a guard who notices sneaky messages even when disguised | normalisation, base64 rescan, heuristic limits (ADR-0014) |
| 16 | (reserved) | see open point below | |

(Only 15 distinct sections are needed: fallback and SSE are two diagrams but may stay separate sections; recount to 16 by splitting "Component architecture" and "Layering" as listed. Final count = every diagram in `docs/diagrams/README.md` index except the two development boards.)

## How to write (facts, not guesses)
- Source every claim from the existing docs already verified this session: `docs/architecture.md` sections, ADRs 0001-0014 (especially their Decision and Consequences), and the diagram JSON `cards` in `docs/diagrams/archify/*.json`. Do not re-derive code behaviour; where a number appears (8 turns, 2 repairs, 0.35 floor, 1536 dims, 30 eval questions) copy it from those docs.
- Interviewer text must name the trade-off and the "not built" gap per diagram (policy engine/Rego, tracing, audit trail, end-to-end eval, long-term memory not wired to HTTP, no import-linter).
- Child text: one analogy per diagram, short sentences, no acronyms.
- Keep word counts honest: check with `wc -w` per section after writing.

## Steps (one commit per task, per user preference)
1. Write `docs/diagrams/explained.md` for diagrams 1-8 (commit).
2. Add diagrams 9-16 (commit).
3. Link it from `docs/diagrams/README.md` and the root `README.md`; mark in `docs/proposals/diagram-plan.md` status note (commit).
4. Push to `add_diagrams` only when the user asks (the branch's earlier PR #38 is merged, so a new PR is needed).

## Verification
- Every section has the three parts and both texts are within 120-150 / 200-250 words (`wc -w` per section, script over the file).
- Every "Diagram:" link resolves to an existing file and anchor (grep the anchors in `architecture.md` and the ADRs).
- Each "not built" claim matches the current stubs (`policy_engine.py`, `tracing.py`, `audit_repository.py`, empty `airline_claims.jsonl`, routes not passing `claimant_id`).
- `make lint` unaffected (docs only); pre-commit passes.

## Open point to confirm in review
Recount: the index lists 15 content diagrams once fallback and SSE are counted separately plus the two dev boards (17 rows). If the final count differs from 16 I will say so and cover every non-timeline diagram in the index.
