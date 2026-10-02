"""
Cross-encoder reranker — a second, sharper pass over retrieval candidates.

Hybrid search compares pre-computed summaries of the question and each
chunk. The reranker reads the question and chunk TOGETHER and scores how
well the chunk answers it. Much more accurate, much slower — so it only
runs on the ~20 candidates hybrid search already shortlisted.

Model runs locally: no per-query cost, no third provider in the path.
"""

"""
Cross-encoder reranker — BUILT BUT NOT WIRED INTO THE PIPELINE.

Tested on 2026-10-02 and it made results worse on this corpus:
  - "PGRST116" → promoted the PGRST106 page above the page containing PGRST116
  - "sign in with GitHub" → promoted a "converted account to org" troubleshooting
    page above the actual Login with GitHub guide
  - cost ~5s per query after warmup (roughly doubles total response time)

Likely cause: ms-marco-MiniLM was trained on web-search passages; this corpus is
technical docs with tables and code. It favours short topical pages over longer
reference material that actually contains the answer.

Parked until Phase 5, when the golden dataset can measure whether any reranker
helps. See OBS-003.
"""
from sentence_transformers import CrossEncoder

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Loaded once per process, on first use
_model = None


def _load():
    """Load the cross-encoder. Downloads ~90MB the first time only."""
    global _model
    if _model is None:
        _model = CrossEncoder(MODEL_NAME)
    return _model


def rerank(question, chunks, top_k=5):
    """Re-score chunks against the question and return the best top_k.

    Each chunk gets a 'rerank_score' and keeps its original fields.
    Higher score = more relevant.
    """
    if not chunks:
        return []

    model = _load()

    # The model scores (question, chunk_text) pairs
    pairs = [(question, c["text"]) for c in chunks]
    scores = model.predict(pairs)

    scored = [
        {**chunk, "rerank_score": float(score)}
        for chunk, score in zip(chunks, scores)
    ]

    scored.sort(key=lambda c: c["rerank_score"], reverse=True)
    return scored[:top_k]