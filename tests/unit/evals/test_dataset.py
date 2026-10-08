import pytest

from evals.dataset import EvalQuestion, GoldSection, load_questions, resolve_gold
from ombuds.features.claims_triage.rag.ingest import KB_SEED_DIR


def test_the_shipped_dataset_loads_with_a_sensible_mix():
    questions = load_questions()
    assert 20 <= len(questions) <= 30
    assert any(q.kind == "off_topic" for q in questions)
    assert any(q.kind == "answerable" for q in questions)


def test_every_gold_section_resolves_to_a_chunk_in_the_kb_seed():
    for question in load_questions():
        assert bool(resolve_gold(question, KB_SEED_DIR)) == (question.kind == "answerable")


def test_resolve_gold_fails_loudly_for_an_unknown_heading():
    question = EvalQuestion(
        id="x",
        question="q",
        kind="answerable",
        gold=(GoldSection(source="eu261_summary.md", heading="No such section"),),
    )
    with pytest.raises(ValueError, match="No such section"):
        resolve_gold(question, KB_SEED_DIR)


def test_load_questions_rejects_an_answerable_row_without_gold(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": "a", "question": "q", "kind": "answerable", "gold": []}\n')
    with pytest.raises(ValueError, match="need gold"):
        load_questions(path)
