from evals.dataset import EvalQuestion, GoldSection
from evals.retrieval_metrics import RankedHit
from evals.run_evals import report

QUESTIONS = [
    EvalQuestion(id="a", question="q a", kind="answerable", gold=(GoldSection(source="d.md", heading="H"),)),
    EvalQuestion(id="b", question="q b", kind="off_topic"),
]
GOLD = {"a": {("d.md", 0)}, "b": set()}


def test_report_shows_separation_and_no_misses_when_the_floor_is_clean():
    hits = {
        "a": [RankedHit(source="d.md", chunk_index=0, score=0.6)],
        "b": [RankedHit(source="d.md", chunk_index=1, score=0.1)],
    }
    text = report(QUESTIONS, hits, GOLD)
    assert "lowest best-gold score:   0.600" in text
    assert "highest off-topic score:  0.100" in text
    assert "  none" in text


def test_report_lists_an_answerable_question_whose_gold_falls_under_the_floor():
    hits = {"a": [RankedHit(source="d.md", chunk_index=0, score=0.1)], "b": []}
    text = report(QUESTIONS, hits, GOLD)
    assert "a: q a" in text
