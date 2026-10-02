"""
Hybrid search — vector + BM25 fused with weighted Reciprocal Rank Fusion,
boosted by document type, then capped so no single document dominates.

Vectors handle paraphrase and intent; BM25 handles exact tokens
(error codes, function names). They fail in opposite directions,
so fusing them covers both.

Run:  python -m retrieval.hybrid_search "your question"
"""

import sys

from retrieval.search import search as vector_search
from retrieval.keyword_search import keyword_search

RRF_K = 60               # standard constant from the RRF paper
CANDIDATES = 10          # fetch this many from each retriever before fusing
VECTOR_WEIGHT = 1.0      # primary retriever: handles paraphrase and intent
BM25_WEIGHT = 0.5        # specialist: rescues exact tokens, shouldn't override
MAX_PER_DOC = 2          # diversity cap — no document fills more than 2 slots
TROUBLESHOOT_BOOST = 1.0 # disabled — see DEC-015. Re-evaluate with eval set.


PROBLEM_WORDS = {
    "error", "errors", "failing", "failed", "fails", "broken", "issue",
    "problem", "why", "not", "cannot", "can't", "wont", "won't",
    "doesn't", "doesnt", "stuck", "wrong", "fix", "debug", "troubleshoot",
}


def is_problem_query(question):
    """True if the question looks like a problem report rather than a how-to."""
    words = set(question.lower().replace("?", " ").replace(",", " ").split())
    return bool(words & PROBLEM_WORDS)


def doc_of(chunk_id):
    """Get the document a chunk belongs to.

    chunk_id = 'guides__auth__social-login__auth-github__2'
    document = 'guides__auth__social-login__auth-github'
    """
    return chunk_id.rsplit("__", 1)[0]


def cap_per_doc(ranked, top_k, max_per_doc=MAX_PER_DOC):
    """Walk the ranked list, keeping at most max_per_doc chunks per document."""
    kept = []
    counts = {}
    for chunk in ranked:
        doc = doc_of(chunk["chunk_id"])
        if counts.get(doc, 0) < max_per_doc:
            kept.append(chunk)
            counts[doc] = counts.get(doc, 0) + 1
        if len(kept) == top_k:
            break
    return kept


def hybrid_search(question, top_k=5, candidates=CANDIDATES):
    """Fuse vector and keyword rankings, boost by doc type, cap per document."""

    vector_hits = vector_search(question, top_k=candidates)
    keyword_hits = keyword_search(question, top_k=candidates)

    fused = {}

    def add(hits, source, weight):
        for rank, hit in enumerate(hits, 1):          # rank starts at 1
            cid = hit["chunk_id"]
            if cid not in fused:
                fused[cid] = {
                    **hit,
                    "rrf_score": 0.0,
                    "vector_rank": None,
                    "bm25_rank": None,
                }
            fused[cid]["rrf_score"] += weight / (RRF_K + rank)
            fused[cid][f"{source}_rank"] = rank

    add(vector_hits, "vector", VECTOR_WEIGHT)
    add(keyword_hits, "bm25", BM25_WEIGHT)

    # Soft boost: problem-shaped questions favour troubleshooting docs.
    # A boost, not a filter — guides can still win, and sometimes should.
    problem = is_problem_query(question)
    for chunk in fused.values():
        chunk["boosted"] = False
        if problem and chunk["doc_type"] == "troubleshooting":
            chunk["rrf_score"] *= TROUBLESHOOT_BOOST
            chunk["boosted"] = True

    ranked = sorted(fused.values(), key=lambda c: c["rrf_score"], reverse=True)
    return cap_per_doc(ranked, top_k)


def main():
    if len(sys.argv) < 2:
        print('Usage: python -m retrieval.hybrid_search "your question"')
        return

    question = sys.argv[1]
    results = hybrid_search(question)

    problem = is_problem_query(question)
    print(f"\nQUESTION: {question}")
    print(f"problem-shaped: {problem}" + ("  → troubleshooting boosted" if problem else ""))
    print("=" * 70)

    for i, r in enumerate(results, 1):
        v = r["vector_rank"] or "-"
        b = r["bm25_rank"] or "-"
        marks = ""
        if r["vector_rank"] and r["bm25_rank"]:
            marks += "  ← both"
        if r.get("boosted"):
            marks += "  ⬆ boosted"
        preview = r["text"].replace("\n", " ")[:85]
        print(f"\n[{i}] rrf {r['rrf_score']:.5f}  |  {r['doc_type'][:15]:<15} vec #{v}  bm25 #{b}{marks}")
        print(f"    {r['title']}")
        print(f"    {preview}...")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()