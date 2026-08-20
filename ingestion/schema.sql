-- Schema for the LLM Reliability Platform chunk store
-- Run:  docker compose exec -T db psql -U postgres -d llm_reliability < ingestion/schema.sql

-- Enable pgvector (vector storage + similarity search)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id            SERIAL PRIMARY KEY,          -- database's internal key
    chunk_id      TEXT UNIQUE NOT NULL,        -- our business key; UNIQUE = re-run guard
    doc_id        TEXT NOT NULL,
    title         TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    url           TEXT,                        -- nullable: partials have no standalone page
    doc_type      TEXT NOT NULL,               -- guide / troubleshooting / partial
    chunk_index   INT NOT NULL,
    total_chunks  INT NOT NULL,
    text          TEXT NOT NULL,
    token_count   INT NOT NULL,
    embedding     VECTOR(1536),                -- text-embedding-3-small; nullable until filled
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Regular B-tree index for metadata filtering (NOT a vector index — see DEC-008)
CREATE INDEX IF NOT EXISTS idx_chunks_doc_type ON chunks(doc_type);