"""
BM25 keyword search over the chunk store.

Complements vector search: embeddings blur exact tokens (error codes,
function names), while BM25 weights rare terms heavily. Built in memory
from the database so it can never go stale.
"""

import os
import re

import psycopg2
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Module-level cache — built once per process
_bm25 = None
_chunks = None


def tokenize(text):
    """Split text into lowercase tokens, keeping code-ish tokens intact.

    Error codes (PGRST116), function names (signInWithOAuth) and config
    keys (external_github_enabled) are exactly what BM25 is good at, so
    we keep underscores and digits rather than stripping them.
    """
    return re.findall(r"[a-z0-9_]+", text.lower())


def _load():
    """Load all chunks from the database and build the BM25 index."""
    global _bm25, _chunks

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT chunk_id, title, url, doc_type, text
        FROM chunks
        ORDER BY id;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    _chunks = [
        {"chunk_id": r[0], "title": r[1], "url": r[2], "doc_type": r[3], "text": r[4]}
        for r in rows
    ]

    corpus = [tokenize(c["text"]) for c in _chunks]
    _bm25 = BM25Okapi(corpus)

    return _bm25, _chunks


def keyword_search(question, top_k=5):
    """Return the top_k chunks by BM25 keyword relevance."""
    global _bm25, _chunks
    if _bm25 is None:
        _load()

    scores = _bm25.get_scores(tokenize(question))

    # Drop zero-score chunks — they contain none of the query terms.
    # Returning them pads the list with noise that RRF would treat as signal.
    scored = [(c, s) for c, s in zip(_chunks, scores) if s > 0]
    ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)[:top_k]

    return [{**chunk, "bm25_score": float(score)} for chunk, score in ranked]

if __name__ == "__main__":
    import sys

    question = sys.argv[1] if len(sys.argv) > 1 else "PGRST116"
    results = keyword_search(question)

    print(f"\nQUERY: {question}\n" + "=" * 70)
    for i, r in enumerate(results, 1):
        preview = r["text"].replace("\n", " ")[:100]
        print(f"\n[{i}] score {r['bm25_score']:.3f}  |  {r['doc_type']}")
        print(f"    {r['title']}")
        print(f"    {preview}...")