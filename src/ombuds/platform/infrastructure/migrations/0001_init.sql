-- Initial schema (ADR-0010). Embedding dimension 1536 must match EMBEDDING_DIM in vector_store.py.
CREATE EXTENSION IF NOT EXISTS vector;

-- One row per (action, payload): the dedup key from ADR-0009 is the UNIQUE constraint, so a retried
-- submit is an INSERT ... ON CONFLICT rather than a read-then-write race.
CREATE TABLE approval_requests (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    action      TEXT NOT NULL CHECK (action IN ('log_claim', 'issue_payment')),
    payload     JSONB NOT NULL,
    payload_key TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied', 'executed')),
    approver    TEXT,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (action, payload_key)
);
CREATE INDEX approval_requests_pending_idx ON approval_requests (created_at) WHERE status = 'pending';

-- Server-issued claims; an external MCP client's claim_id is validated against this table (ADR-0009).
CREATE TABLE claims (
    claim_id   TEXT PRIMARY KEY,
    facts      JSONB NOT NULL,
    decision   JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE long_term_memory (
    claimant_id TEXT PRIMARY KEY,
    facts       JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE kb_chunks (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(1536) NOT NULL,
    UNIQUE (source, chunk_index)
);
CREATE INDEX kb_chunks_embedding_idx ON kb_chunks USING hnsw (embedding vector_cosine_ops);
