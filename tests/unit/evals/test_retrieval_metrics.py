import pytest

from evals.retrieval_metrics import (
    RankedHit,
    first_relevant_rank,
    hit_rate_at_k,
    mean_reciprocal_rank,
    rejection_rate,
)


def hit(chunk_index: int, score: float, source: str = "a.md") -> RankedHit:
    return RankedHit(source=source, chunk_index=chunk_index, score=score)


GOLD = {("a.md", 2)}


def test_first_relevant_rank_is_one_based_position_of_the_gold_chunk():
    hits = [hit(0, 0.9), hit(2, 0.7), hit(1, 0.5)]
    assert first_relevant_rank(hits, GOLD) == 2


def test_first_relevant_rank_is_none_when_gold_is_absent():
    assert first_relevant_rank([hit(0, 0.9), hit(1, 0.5)], GOLD) is None


def test_first_relevant_rank_ignores_the_same_index_in_another_source():
    assert first_relevant_rank([hit(2, 0.9, source="b.md")], GOLD) is None


def test_first_relevant_rank_counts_any_of_several_gold_chunks():
    assert first_relevant_rank([hit(0, 0.9), hit(5, 0.8)], {("a.md", 2), ("a.md", 5)}) == 2


def test_first_relevant_rank_drops_hits_below_the_floor_before_ranking():
    hits = [hit(0, 0.1), hit(2, 0.3)]
    assert first_relevant_rank(hits, GOLD, min_score=0.2) == 1
    assert first_relevant_rank(hits, GOLD, min_score=0.5) is None


@pytest.mark.parametrize(("k", "expected"), [(1, 0.25), (3, 0.5), (5, 0.75)])
def test_hit_rate_at_k_counts_ranks_within_k(k, expected):
    assert hit_rate_at_k([1, 3, None, 5], k) == pytest.approx(expected)


def test_mean_reciprocal_rank_treats_a_miss_as_zero():
    assert mean_reciprocal_rank([1, 2, None]) == pytest.approx((1 + 0.5 + 0) / 3)


def test_metrics_on_no_questions_are_zero():
    assert hit_rate_at_k([], 5) == 0.0
    assert mean_reciprocal_rank([]) == 0.0
    assert rejection_rate([], 0.2) == 0.0


def test_rejection_rate_counts_questions_with_nothing_at_or_above_the_floor():
    off_topic = [[hit(0, 0.15), hit(1, 0.1)], [hit(0, 0.25)], []]
    assert rejection_rate(off_topic, 0.2) == pytest.approx(2 / 3)
    assert rejection_rate(off_topic, 0.25) == pytest.approx(2 / 3)
    assert rejection_rate(off_topic, 0.26) == 1.0
