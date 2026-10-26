# Code style

Formatting, import order, naming and type correctness are enforced by tools — don't debate them here or in review:

| Concern | Tool | Config |
|---|---|---|
| Editor basics (indent, EOL, whitespace) | EditorConfig | `.editorconfig` |
| Formatting, lint, import order, naming | ruff | `[tool.ruff]` in `pyproject.toml` |
| Types | mypy (strict, pydantic plugin) | `[tool.mypy]` in `pyproject.toml` |
| All of the above, before every commit | pre-commit | `.pre-commit-config.yaml` — run `uv run pre-commit install` once |

`make lint` runs the checks, `make format` fixes what can be fixed, `make test` runs lint then tests.

This document covers only the judgement calls a tool can't make.

## Structure

- **The module is the namespace.** Put related classes and functions side by side at top level. Don't nest classes inside a "main" class, and don't write a class of only `@staticmethod`s — that's a module.
- **Functions by default; a class when there is state** to hold or several implementations to swap. Data goes in Pydantic models or dataclasses, behaviour in functions.
- **One reason to change per module.** Data shape and the logic over it are separate files — e.g. `verticals/airline/evidence_schema.py` (the facts) vs `rules.py` (what the facts mean).
- **Import direction is `features → platform → domain`**, never the reverse (ADR-0002). Within a vertical, `rules.py` imports `evidence_schema.py`, not the other way round.
- **Leading underscore = private to the module.** Tests exercise the public API; if a private helper needs its own test, it probably wants to be public or in its own module.

## Data and types

- Type-hint everything (mypy strict enforces it in `src/`).
- **Pydantic models for anything crossing a layer boundary**: API payloads, tool arguments/results, structured LLM output. Plain types inside a layer are fine.
- Models are **`frozen=True` by default**; make one mutable only with a reason.
- Model fields are **facts, not judgments** — `notice_given: timedelta`, not `is_late_notice: bool`. The judgment belongs in the rules.
- Use `StrEnum` for closed sets of values that get serialized (reason codes, types), not bare strings.
- Name units in identifiers when the type doesn't carry them: `distance_km`, `compensation_eur`. Use `timedelta` for durations, never bare ints of hours.

## Business rules

- Business rules (EU261 distance tiers, notice-period exemptions, SLA thresholds) live only in `domain/` or `features/<feature>/verticals/<vertical>/rules.py` — never inline in a prompt, a tool, or an agent node. A threshold hardcoded in `agent/nodes/` is a bug, not a shortcut.
- Thresholds are named module-level `UPPER_CASE` constants, not magic numbers in conditions.
- Rule functions are pure: facts in, result out, no I/O, no clock, no randomness. That's what makes them unit-testable and safe for an LLM to call.
- Outcomes carry machine-readable reason codes so an LLM can cite *why* without re-deriving it.

## Docstrings and comments

- **Docstrings on every module and every public class/function.** First line says what it does; add a paragraph only for non-obvious behaviour (ordering, edge cases, what's deliberately not handled). Don't restate the type hints in prose.
- **Comments explain *why*, never *what*.** Good: `# Art. 7(2) applies to re-routing, which only exists for cancellations`. Bad: `# check if delay`.
- Cite the source of external rules (regulation article, ADR number) — it's the fastest way to verify the code is right.

## Errors

- Catch specific exceptions only. No bare `except:` and no `except Exception:` — each provider adapter (e.g. `platform/ai/providers/anthropic.py`) translates its own SDK's retryable failures into the shared `ProviderUnavailableError` at its own boundary, so `platform/ai/providers/fallback.py`'s retry/fallover logic catches that one type, not `Exception` (ADR-0006).
- Domain error types live in `domain/errors.py`. Raise at the point of detection; translate to HTTP status only in `api/`.
- Don't use exceptions for expected outcomes: "not eligible" is a result, not an error.

## Tests

- `tests/unit/` mirrors `src/ombuds/`, one test module per source module, no I/O.
- Name tests as the behaviour they pin: `test_delay_threshold_is_three_hours`, not `test_evaluate_2`.
- Test boundaries explicitly — the value on each side of every threshold — with `pytest.mark.parametrize`.
- Build inputs from one valid baseline factory plus overrides (see `disruption(**overrides)` in `test_rules.py`), so each test shows only what differs.
- Every new tool in `features/<feature>/tools/` needs a unit test, and once it's agent-callable, an entry in the eval dataset it affects.

## Diagrams
Every diagram has its own folder with one page, `docs/diagrams/<slug>/README.md`, built from `docs/diagrams/_template.md`: title, version, date, pinned commit, the diagram, a child and an interviewer explanation. A Mermaid diagram lives in that page's `mermaid` block (with a front-matter `title:` carrying version and date); an archify diagram keeps its `.json` and `.png` next to that page and is rebuilt with `docs/diagrams/render_archify.py`. ADRs and `architecture.md` link to the page with a one-line `Diagram: [Title vX.Y](../diagrams/<slug>/README.md)` instead of pasting the diagram. Adding a diagram means a new folder and page, a row in the `docs/diagrams/README.md` index, and the link from the ADR it illustrates. When the system a diagram shows changes, bump its version and date in the page, the diagram title and the index.
