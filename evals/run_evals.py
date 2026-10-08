"""Retrieval eval: score the real retriever on the labelled questions and sweep the relevance floor.

Needs OPENAI_API_KEY and an ingested knowledge base (`make eval` starts the db and ingests first).
Searches once per question with no floor, then applies each candidate floor to those saved scores.
"""

from evals.dataset import EvalQuestion, load_questions, resolve_gold
from evals.retrieval_metrics import (
    ChunkKey,
    RankedHit,
    first_relevant_rank,
    hit_rate_at_k,
    mean_reciprocal_rank,
    rejection_rate,
)
from ombuds import config
from ombuds.features.claims_triage.rag.ingest import KB_SEED_DIR
from ombuds.features.claims_triage.rag.retriever import DEFAULT_MIN_SCORE, Retriever
from ombuds.platform.ai.embeddings import OpenAIEmbedder
from ombuds.platform.infrastructure.postgres import create_pool
from ombuds.platform.infrastructure.vector_store import PgVectorStore

TOP_K = 5
FLOORS = [round(step * 0.05, 2) for step in range(0, 11)]  # 0.00 .. 0.50
SHOWN_ON_MISS = 3


def collect_hits(retriever: Retriever, questions: list[EvalQuestion]) -> dict[str, list[RankedHit]]:
    """Top-`TOP_K` hits per question id; `retriever` must be built with `min_score=0.0` to keep every score."""
    return {
        q.id: [
            RankedHit(source=c.source, chunk_index=c.chunk_index, score=c.score)
            for c in retriever.retrieve(q.question, TOP_K)
        ]
        for q in questions
    }


def report(questions: list[EvalQuestion], hits: dict[str, list[RankedHit]], gold: dict[str, set[ChunkKey]]) -> str:
    """Format the floor sweep, score separation and the answerable questions the current floor misses."""
    answerable = [q for q in questions if q.kind == "answerable"]
    off_topic = [q for q in questions if q.kind == "off_topic"]
    lines = [f"{len(answerable)} answerable + {len(off_topic)} off-topic questions, top_k={TOP_K}", ""]
    lines.append("floor  hit@1  hit@3  hit@5   MRR  off-topic rejected")
    for floor in FLOORS:
        ranks = [first_relevant_rank(hits[q.id], gold[q.id], floor) for q in answerable]
        rejected = rejection_rate([hits[q.id] for q in off_topic], floor)
        lines.append(
            f"{floor:5.2f}  {hit_rate_at_k(ranks, 1):5.2f}  {hit_rate_at_k(ranks, 3):5.2f}  "
            f"{hit_rate_at_k(ranks, 5):5.2f}  {mean_reciprocal_rank(ranks):4.2f}  {rejected:18.2f}"
        )

    # Best score of a gold chunk per answerable question vs best score of anything for off-topic ones:
    # a floor can separate them only if the lowest of the first stays above the highest of the second.
    gold_best = {q.id: max((h.score for h in hits[q.id] if h.key in gold[q.id]), default=None) for q in answerable}
    found = [s for s in gold_best.values() if s is not None]
    off_best = [max((h.score for h in hits[q.id]), default=0.0) for q in off_topic]
    lines += ["", f"lowest best-gold score:   {min(found, default=0.0):.3f}"]
    lines.append(f"highest off-topic score:  {max(off_best, default=0.0):.3f}")

    lines += ["", f"misses at the current floor ({DEFAULT_MIN_SCORE}):"]
    missed = False
    for q in answerable:
        if first_relevant_rank(hits[q.id], gold[q.id], DEFAULT_MIN_SCORE) is None:
            missed = True
            got = ", ".join(f"{h.source}#{h.chunk_index}={h.score:.2f}" for h in hits[q.id][:SHOWN_ON_MISS]) or "-"
            lines.append(f"  {q.id}: {q.question}\n    gold {sorted(gold[q.id])}  got {got}")
    if not missed:
        lines.append("  none")
    return "\n".join(lines)


def main() -> None:
    """Run the retrieval eval against the configured Postgres and embedding model and print the report."""
    questions = load_questions()
    gold = {q.id: resolve_gold(q, KB_SEED_DIR) for q in questions}
    pool = create_pool(config.DATABASE_URL, config.DATABASE_POOL_MAX_SIZE)
    try:
        retriever = Retriever(OpenAIEmbedder(config.EMBEDDING_MODEL), PgVectorStore(pool), min_score=0.0)
        print(report(questions, collect_hits(retriever, questions), gold))
    finally:
        pool.close()


if __name__ == "__main__":
    main()
