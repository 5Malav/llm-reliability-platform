"""
Load chunks + embeddings into Postgres.

Joins chunks.json and embeddings.json on chunk_id, then upserts each
row into the chunks table. Safe to re-run (upsert, not insert).

Run:  python ingestion/load_to_db.py
"""

import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

load_dotenv()

CHUNKS_FILE = Path("ingestion/data/chunks.json")
EMBEDDINGS_FILE = Path("ingestion/data/embeddings.json")
DATABASE_URL = os.getenv("DATABASE_URL")
BATCH_SIZE = 500

INSERT_SQL = """
INSERT INTO chunks (
    chunk_id, doc_id, title, source_path, url, doc_type,
    chunk_index, total_chunks, text, token_count, embedding
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (chunk_id) DO UPDATE SET
    text        = EXCLUDED.text,
    embedding   = EXCLUDED.embedding,
    token_count = EXCLUDED.token_count;
"""


def main():
    chunks = json.loads(CHUNKS_FILE.read_text())
    embeddings = json.loads(EMBEDDINGS_FILE.read_text())

    # Build a lookup: chunk_id -> vector
    vectors = {e["chunk_id"]: e["embedding"] for e in embeddings}

    print(f"Chunks:     {len(chunks)}")
    print(f"Embeddings: {len(vectors)}")

    # Join, and fail loudly if anything is missing its vector
    rows = []
    missing = []
    for c in chunks:
        vec = vectors.get(c["chunk_id"])
        if vec is None:
            missing.append(c["chunk_id"])
            continue
        rows.append((
            c["chunk_id"], c["doc_id"], c["title"], c["source_path"],
            c["url"], c["doc_type"], c["chunk_index"], c["total_chunks"],
            c["text"], c["token_count"], vec,
        ))

    if missing:
        raise ValueError(f"{len(missing)} chunks have no embedding, e.g. {missing[:3]}")

    print(f"Rows to load: {len(rows)}")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    execute_batch(cur, INSERT_SQL, rows, page_size=BATCH_SIZE)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM chunks;")
    total = cur.fetchone()[0]

    cur.close()
    conn.close()

    print("\n--- Load complete ---")
    print(f"Rows in database: {total}")


if __name__ == "__main__":
    main()