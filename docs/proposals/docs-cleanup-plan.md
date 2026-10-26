# Docs cleanup plan

**Status: proposed (2026-10-26).** Produced by running [docs-cleanup-prompt.md](docs-cleanup-prompt.md) on branch `docs-simplification`. Nothing here is applied yet.

`docs/` is 11 MB and about 3,200 lines of markdown. Roughly 10 MB is diagram binaries (20 diagram folders; the six archify ones are ~1.1 MB each, the development board 2.7 MB). Deleting the diagram `.html` files alone removes 7.4 MB. Everything below was checked against `tasks.md` (W1–W6 ticked, W7 has one open item), the ADR list and inbound links. Where I judged from headers only, it says **unverified**.

## Summary

| Action | Files | Notes |
|---|---|---|
| DELETE | 5 | the first W4 review, the W4 order plan, the security-hardening plan, the diagram plan (after a 5-line move), the e2e plan (merge into report) |
| DELETE (build output) | 9 | every diagram `.html`, 7.4 MB; keep `.json`, `README.md`, `.png` |
| MERGE | 2 | `backlog.md` into `tasks.md`; e2e plan into its report |
| UPDATE | 4 | `demo-script.md`, `diagrams/README.md` header text, `task_summaries.md` and `backlog.md` source links, `tasks.md` review link |
| TRIM | 2 | `task_summaries.md` (648 lines), `glossary.md` (140) |
| ASK | 4 | rev2 review, `build_and_explain.md`, the 3 overlapping archify diagrams, the development board |
| KEEP | the rest | ADRs, `architecture.md`, `code-style.md`, `developer-guide.md`, `db-queries.md`, most diagram pages |

## `docs/proposals/` (4 files, all HISTORY)

Every plan here is finished. The living knowledge already sits in ADRs, `tasks.md` and the diagram pages.

| File | Action | Evidence |
|---|---|---|
| `w4-implementation-order.md` | **DELETE** | Status "done (2026-10-18)". Rego, audit and tracing shipped as ADR-0015/0016/0017, which hold the reasoning. |
| `security-hardening.md` | **DELETE** | Status line still says "proposed", but all five tasks shipped: ports and DB default (W5), auth (ADR-0019), gitleaks/CI/push protection and the HTML skim (W6, `tasks.md`). The "weak defaults" it describes no longer exist, so it is misleading as it stands. |
| `diagram-plan.md` | **DELETE** (after moving 2 lines) | Header says "This plan is history"; ~55 of its 70 lines are the "original plan, for reference". Its status table duplicates `diagrams/README.md`. Keep only: "Not drawn yet: tracing, Rego policy, audit trail, agent-eval flow" — move that to `diagrams/README.md`. Inbound: `diagrams/README.md`? (unverified), `task_summaries.md`. |
| `e2e-real-case-test.md` | **MERGE** into `progress/e2e-report-2026-10-26.md`, then delete | Done 2026-10-26; the report already states the three cases and results. Keep the plan's "Cost control" and "Not covered, by design" paragraphs as a short "How to rerun" at the top of the report. Inbound: the report (links back). |
| `docs-cleanup-prompt.md`, this plan | KEEP until executed, then delete the plan | New. |

After this the folder holds only live proposals (none right now); keep the folder for future ones.

## `docs/progress/`

| File | Class | Action | Evidence |
|---|---|---|---|
| `w4_review_pre_w5_plan.md` (284 lines) | HISTORY | **DELETE** | Superseded by rev2, which says it is a refresh and carries the open items. Its P-1..P-4 became the W5 tasks, all ticked. Git keeps it (`360b5c5`). Fix links: `backlog.md:15`, `task_summaries.md:632`, rev2 line 5. |
| `w4_review_pre_w5_plan_rev2.md` (254) | HISTORY | **ASK**, lean delete | Every finding (F-01..F-06) maps to a W5/W6 task now ticked. Its only live value is "claims vs code" tables, which are point-in-time. Recommend delete once the links in `tasks.md:53`, `backlog.md:26`, `task_summaries.md:615` are repointed to the git commit. Same logic that already deleted the W1–W3 reviews (see `backlog.md` header). |
| `backlog.md` (29) | SNAPSHOT | **MERGE** into `tasks.md`, then delete | Nearly every row is struck through as done. Open rows: frozen settings object, OPA healthcheck (the W5 task says done: verify and drop the row, **unverified**). Move what is still open to a "Later" list at the bottom of `tasks.md`. Inbound: `tasks.md:53`. |
| `e2e-report-2026-10-26.md` | HISTORY | KEEP | The one record of a real run, plus the two findings (agent did not file on the first try; audit rows for read-only tools lack `claim_id`). Check both became tasks; if not, add them to `tasks.md` Week 7. |
| `tasks.md` (92) | SNAPSHOT | UPDATE | Add the e2e findings and the merged backlog items. Header says "snapshot of Notion, last synced 2026-09-24": decide if Notion is still the source (ASK). |
| `task_summaries.md` (648) | SNAPSHOT | **TRIM** | 6x larger than any other file. It is a recap "for future-you, not documentation". Suggest: keep entries for W4–W6 only where they carry a non-obvious decision; drop file lists and library lines already in code and ADRs. Target ~250 lines. Needs your call on how much interview recall you want to keep (ASK). |
| `glossary.md` (140) | LIVING | TRIM lightly | Library glossary tied to `task_summaries.md` anchors (`↳ First seen` links). If summaries are trimmed, those anchors break: do the glossary in the same commit. |

## `docs/guide/`

| File | Action | Evidence |
|---|---|---|
| `developer-guide.md`, `db-queries.md` | KEEP | Referenced by AGENTS.md and the demo script; commands match the Makefile status line. |
| `demo-script.md` | **UPDATE** | Line 3 says "end of Week 4"; the "Planned: Week 5/6" sections (lines 87–98) are all shipped (recovery route, auth, audit completion, `make eval-agent`, CI). Turn them into real steps or delete the headings, and bump the date. Section 2's curl already uses the triage token, so the middle is current. |
| `build_and_explain.md` | **ASK** | Personal interview-prep method ("write it in its Notion page", "4-week build"). Not project knowledge. Options: move out of the repo to Notion, or keep as is. Inbound: `task_summaries.md` only (unverified). |

## `docs/diagrams/` (10 MB)

| Item | Action | Evidence |
|---|---|---|
| 12 Mermaid pages (`approval-lifecycle`, `triage-graph`, `layering`, `data-model`, `provider-fallback`, `sse-event-order`, `compose-startup`, `memory-flow`, `prompt-versioning`, `injection-detection`, …) | KEEP | Text only, a few KB, linked from ADRs. |
| `architecture`, `triage-approval-flow`, `guardrails-pipeline`, `rag-evals-pipeline`, `mcp-boundary` | KEEP | Each is tied to ADRs and linked from `architecture.md` / README. |
| `artifact-map`, `claim-sequence`, `development-overview` (2.7 MB) | **ASK** | Three more archify pages for the same system as `architecture` + `triage-approval-flow`. **Unverified overlap**: I read their headers only. Ask whether each answers a different question. The development board is a build-history timeline (HISTORY): strongest delete candidate, and it drags `development_board_gen.py` (226 lines) with it. Checking inbound: ADR-0003/0009/0010/0015/0016/0017 and `architecture.md` link `artifact-map`/`development-overview`, so those links need repointing. |
| `diagrams/README.md` | UPDATE | Add the "not drawn yet" line from `diagram-plan.md`; drop rows for anything deleted. |

### Delete every diagram `.html`, keep `.json`, `README.md` and `.png` (decided)

The 9 committed `.html` files weigh **7.4 MB** of the 11 MB in `docs/` (about 800 KB each). Each is regenerated from its `.json` by `render_archify.py`, and the `.png` embedded in each page is what readers see. So the HTML is a build output, not source.

What must change with it (all found by grep):
- **Delete 9 files:** `architecture`, `artifact-map`, `claim-sequence`, `guardrails-pipeline`, `mcp-boundary`, `rag-evals-pipeline`, `triage-approval-flow` (one each) and `development-overview.html` + `development-overview-v2.html`.
- **Diagram pages:** 9 lines of the form "Interactive version: `<slug>.html` · Source: `<slug>.json`" would link to a missing file. Drop the "Interactive version" link in `architecture`, `artifact-map`, `claim-sequence`, `guardrails-pipeline`, `mcp-boundary`, `rag-evals-pipeline`, `triage-approval-flow` and both lines in `development-overview/README.md` (lines 18, 42). Keep "Source: …json".
- **Regenerate sections:** six pages say "rewrites the `.html` and `.png` … The HTML stays under the repo's 10x…" (`architecture:35`, `guardrails-pipeline:35`, `mcp-boundary:35`, `rag-evals-pipeline:35`, `triage-approval-flow:35`, `development-overview:69`). Reword to "rewrites the `.png`".
- **`render_archify.py`:** line 67 copies the HTML into the diagram folder. Remove that line and update the docstring (line 1), so a re-render no longer brings the file back. It still builds the HTML in a temp dir to take the screenshot.
- **Docs that name the file type:** `diagrams/README.md` lines 8, 10 and 47, and `_template.md:7` (the archify comment). `development_board_gen.py:204` writes to `/tmp`, so no change.
- **Not touched:** `code-style.md:61`, `task_summaries.md:537` and `glossary.md:106` mention `.html` generically; reword only if they promise the file exists (check while editing).
- **Cost of the choice:** the interactive pan/zoom view is gone from the repo. Anyone who wants it runs `render_archify.py` (needs node, archify, Chrome). The PNG stays the reference.
- **Side benefit:** the W6 "skim `*.html` for local paths" check no longer has files to skim.

Saves 7.4 MB, leaving about 3.6 MB; deleting the development board as well (`.json` + `.png` ~ 0.9 MB, see ASK above) is a separate decision.

## Root and tooling docs

| File | Action | Evidence |
|---|---|---|
| `README.md` (120), `AGENTS.md`, `CLAUDE.md` | KEEP | Living. `AGENTS.md` "Status (2026-10-15)" line is older than W6 work: UPDATE the date after the cleanup. |
| `docs/architecture.md`, `code-style.md` | KEEP | Living. |
| ADRs 0000–0019 | KEEP | Only change to consider: none. 0008 is correctly `superseded by 0009`. |
| `.claude/skills/*` | KEEP | Tooling, not docs. |

## Proposed commits (one per task, on `docs-simplification`)

1. Delete `progress/w4_review_pre_w5_plan.md`; repoint `backlog.md:15`, `task_summaries.md:632`, rev2 line 5. *Verify:* `grep -rn "w4_review_pre_w5_plan.md" .` returns nothing.
2. Delete `proposals/w4-implementation-order.md` and `proposals/security-hardening.md`. *Verify:* grep for both names.
3. Move the "not drawn yet" line into `diagrams/README.md`; delete `proposals/diagram-plan.md`; fix `task_summaries.md` links.
4. Merge the e2e plan into its report and delete the plan; repoint the report's backlink.
5. Fold `backlog.md` into `tasks.md` ("Later" list, plus the e2e findings if not tracked); delete `backlog.md`; fix `tasks.md:53`.
6. Update `demo-script.md` (end of W6, planned sections become real steps).
7. After your answers: delete rev2 and fix its three inbound links.
8. After your answers: trim `task_summaries.md` and `glossary.md` together.
9. Delete the 9 diagram `.html` files and fix the pages, `render_archify.py` and the docs listed in "Delete every diagram `.html`". No answers needed. *Verify:* `grep -rn "\.html" docs` returns no link to a missing file; `uv run --with pillow python docs/diagrams/render_archify.py architecture` rewrites only the `.png` and leaves no `.html` in the folder.
10. After your answers: diagram decisions (development board, overlapping archify pages) with inbound-link fixes in the ADRs and `architecture.md`.

Each commit: `grep` for dead links and `make lint` (docs only, but the pre-commit hooks run).

## Questions for you

1. **rev2 review**: delete now (my recommendation), or keep until W7 is done?
2. **`task_summaries.md`**: how much of the per-task recap do you still use for interview prep? That sets how hard to trim.
3. **`build_and_explain.md`**: project doc, or personal method that belongs in Notion?
4. **Diagrams**: is the development board still wanted? Do `artifact-map` and `claim-sequence` each show something `architecture` and `triage-approval-flow` do not?
5. **`tasks.md`**: is Notion still the source of truth (header says snapshot from 2026-09-24)?
