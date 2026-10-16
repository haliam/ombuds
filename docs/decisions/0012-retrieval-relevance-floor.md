# ADR-0012: Retrieval relevance floor of 0.35

**Status:** accepted
**Date:** 2026-10-08

## Context
ADR-0011 shipped `DEFAULT_MIN_SCORE = 0.2` as a guess. `make eval` now runs 30 labelled questions (26 answerable, 4 off-topic, `evals/datasets/airline_retrieval.jsonl`) through the real retriever with `text-embedding-3-small` and sweeps the floor. At 0.2 only 1 of 4 off-topic questions returned nothing, so the floor was not doing its job.

Sweep (top_k=5): hit@5 is 0.96 and MRR 0.84 for every floor up to 0.35; at 0.40 hit@5 falls to 0.92 and at 0.50 to 0.65. Off-topic rejection is 0.25 at 0.2, 0.50 at 0.30-0.35 and 1.00 from 0.40. The lowest best-gold score is 0.384 and the highest off-topic score is 0.389, so no floor separates the two sets perfectly.

## Decision
Set `DEFAULT_MIN_SCORE` to 0.35: the highest floor that costs no recall on the eval set.

## Consequences
- Off-topic rejection doubles (0.25 to 0.50) with no change in hit@k or MRR.
- Half the off-topic questions (the ones about airlines, bags and hotels) still return a weak passage. The model must still judge relevance; the floor is not a guard against irrelevant citations.
- The set is small (4 off-topic rows, 26 answerable) and one question (`scope-2`, hit@5 miss at every floor) is a retrieval failure the floor cannot fix. Treat 0.35 as a measured default, not a precise optimum.
- Revisit when the KB grows beyond three documents, the embedding model changes, or the off-topic set gets larger. Re-run `make eval` and compare.

## Alternatives considered
- **0.40:** rejects every off-topic question but drops one answerable question out of the top 5 for a 0.005 score margin, on a set too small to trust that trade. Preferred recall: a missing citation is worse than a weak one the model can ignore.
- **Keep 0.2:** rejects almost nothing, so the floor was decorative.

See the RAG and evals diagram in [architecture.md](../architecture.md#rag-and-evals).
