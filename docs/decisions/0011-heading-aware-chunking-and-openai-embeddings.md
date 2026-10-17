# ADR-0011: Heading-aware markdown chunking and OpenAI embeddings

**Status:** accepted
**Date:** 2026-10-07

## Context
The RAG pipeline needs a chunking strategy for the airline policy documents and an embedding model. The schema already fixes the vector size at 1536 (ADR-0010). Anthropic offers no embeddings API, so a second provider is unavoidable.

## Decision
- **Chunking:** split markdown at headings, so one chunk never mixes two sections. A section over 1000 characters is packed paragraph by paragraph with its heading repeated on each piece; only a single oversized paragraph is cut mid-text, with 100 characters of overlap. A heading with no body is joined onto the next section.
- **Embeddings:** OpenAI `text-embedding-3-small` (1536 dimensions) behind an `Embedder` Protocol in `platform/ai/embeddings.py`. Its retryable SDK errors become `ProviderUnavailableError`, as for the LLM providers (ADR-0006).
- **Retrieval:** cosine top-k with a relevance floor (`DEFAULT_MIN_SCORE = 0.2`), so an off-topic query returns nothing instead of a weak match to cite. `search_kb` is the only retrieval entry point; passages reach the model only as tool results.
- **Ingest:** each source document is replaced as a whole in one transaction (`replace_source`), so re-ingesting an edited file leaves no stale chunks.

## Consequences
- Citations are meaningful: every chunk is a self-contained, headed section, and `(source, chunk_index)` identifies it.
- The policy documents are short and structured, so a character-based splitter is enough; no tokenizer dependency.
- Embedding needs `OPENAI_API_KEY` and a network call at ingest and at every `search_kb`. An outage surfaces as a tool error the agent can see.
- Switching to another embedding model with a different dimension needs a new migration and a full re-ingest.
- The `0.2` floor was a starting guess; ADR-0012 re-tuned it against the retrieval eval set.

## Alternatives considered
- **Fixed-size sliding windows** — simpler, but splits sections mid-rule and gives citations that start mid-sentence.
- **A local sentence-transformers model** — no API key or cost, but a heavy dependency and a 384/768-dimension schema change.

See the RAG and evals diagram in [architecture.md](../architecture.md#rag-and-evals).
