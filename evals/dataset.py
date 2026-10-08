"""Retrieval eval dataset: load labelled questions and resolve their gold sections to chunk keys."""

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from evals.retrieval_metrics import ChunkKey
from ombuds.features.claims_triage.rag.chunking import chunk_document

RETRIEVAL_DATASET = Path(__file__).parent / "datasets" / "airline_retrieval.jsonl"


class GoldSection(BaseModel):
    """A KB section a question should be answered from, named by file and heading text (no `#`)."""

    model_config = ConfigDict(frozen=True)

    source: str
    heading: str


class EvalQuestion(BaseModel):
    """One labelled question. `off_topic` questions have no gold and should retrieve nothing."""

    model_config = ConfigDict(frozen=True)

    id: str
    question: str
    kind: Literal["answerable", "off_topic"]
    gold: tuple[GoldSection, ...] = ()


def load_questions(path: Path = RETRIEVAL_DATASET) -> list[EvalQuestion]:
    """Read the JSONL dataset, checking that answerable rows have gold and off-topic rows have none."""
    questions = [
        EvalQuestion.model_validate(json.loads(line)) for line in path.read_text().splitlines() if line.strip()
    ]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate question ids in the eval dataset")
    for q in questions:
        if (q.kind == "answerable") != bool(q.gold):
            raise ValueError(f"{q.id}: answerable questions need gold sections, off_topic ones must have none")
    return questions


def resolve_gold(question: EvalQuestion, kb_dir: Path) -> set[ChunkKey]:
    """Map each gold (source, heading) to the (source, chunk_index) of every chunk containing that heading.

    Sections can be split into several chunks, each repeating the heading, so a section may map to more
    than one key. A heading that matches no chunk raises, so a renamed section fails loudly.
    """
    keys: set[ChunkKey] = set()
    for section in question.gold:
        pattern = re.compile(rf"^#{{1,6}}\s+{re.escape(section.heading)}\s*$", re.MULTILINE)
        chunks = chunk_document(section.source, (kb_dir / section.source).read_text())
        found = {(c.source, c.chunk_index) for c in chunks if pattern.search(c.content)}
        if not found:
            raise ValueError(f"{question.id}: no chunk in {section.source} has the heading {section.heading!r}")
        keys |= found
    return keys
