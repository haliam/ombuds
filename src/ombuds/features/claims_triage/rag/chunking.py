"""Chunking: split a markdown policy document into heading-scoped pieces small enough to embed and cite."""

import re

from pydantic import BaseModel, ConfigDict

DEFAULT_MAX_CHARS = 1000
DEFAULT_OVERLAP_CHARS = 100

_HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)


class Chunk(BaseModel):
    """One embeddable piece of a source document. `chunk_index` is its position within `source`."""

    model_config = ConfigDict(frozen=True)

    source: str
    chunk_index: int
    content: str


def chunk_document(
    source: str, text: str, *, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP_CHARS
) -> list[Chunk]:
    """Split `text` into chunks of at most `max_chars`, never mixing two headings' sections.

    A section that fits becomes one chunk. A longer one is packed paragraph by paragraph, with its
    heading repeated on every piece so each chunk is understandable (and citable) on its own. Only a
    single paragraph longer than the budget is cut mid-text, with `overlap` characters shared between
    neighbouring pieces so a sentence cut at the boundary still appears whole in one of them.
    """
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")

    pieces: list[str] = []
    for section in _sections(text):
        pieces.extend(_split_section(section, max_chars, overlap))
    return [Chunk(source=source, chunk_index=index, content=piece) for index, piece in enumerate(pieces)]


def _sections(text: str) -> list[str]:
    """Cut `text` at each markdown heading, keeping the heading line at the top of its section."""
    starts = [match.start() for match in _HEADING.finditer(text)]
    bounds = sorted({0, *starts, len(text)})
    sections = (text[start:end].strip() for start, end in zip(bounds, bounds[1:], strict=False))
    return [section for section in sections if section]


def _split_section(section: str, max_chars: int, overlap: int) -> list[str]:
    if len(section) <= max_chars:
        return [section]

    heading = ""
    body = section
    if _HEADING.match(section):
        heading, _, body = section.partition("\n")
        heading += "\n\n"
    budget = max_chars - len(heading)
    if budget <= overlap:
        raise ValueError("heading leaves no room for body text; raise max_chars")

    pieces: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in body.split("\n\n")):
        if not paragraph:
            continue
        for part in _hard_split(paragraph, budget, overlap):
            candidate = f"{current}\n\n{part}" if current else part
            if len(candidate) <= budget:
                current = candidate
            else:
                pieces.append(current)
                current = part
    if current:
        pieces.append(current)
    return [(heading + piece).strip() for piece in pieces]


def _hard_split(paragraph: str, budget: int, overlap: int) -> list[str]:
    """Return `paragraph` whole if it fits, else overlapping windows of at most `budget` characters."""
    if len(paragraph) <= budget:
        return [paragraph]
    step = budget - overlap
    return [paragraph[start : start + budget] for start in range(0, len(paragraph) - overlap, step)]
