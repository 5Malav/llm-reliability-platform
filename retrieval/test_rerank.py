"""
Compare hybrid search results before and after reranking.

Run:  python -m retrieval.test_rerank "your question"
"""

import sys
import time

from retrieval.hybrid_search import hybrid_search
from retrieval.reranker import rerank


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "PGRST116"

    # Get a wider candidate pool for the reranker to work with
    t0 = time.time()
    candidates = hybrid_search(question, top_k=20)
    retrieval_time = time.time() - t0

    t1 = time.time()
    reranked = rerank(question, candidates, top_k=5)
    rerank_time = time.time() - t1

    print(f"\nQUESTION: {question}")
    print("=" * 72)

    print(f"\nBEFORE rerank (hybrid top 5):")
    for i, c in enumerate(candidates[:5], 1):
        print(f"  [{i}] {c['title'][:60]}")

    print(f"\nAFTER rerank (top 5):")
    for i, c in enumerate(reranked, 1):
        print(f"  [{i}] {c['rerank_score']:7.3f}  {c['title'][:60]}")

    print(f"\nretrieval {retrieval_time:.2f}s  |  rerank {rerank_time:.2f}s")
    print("=" * 72)


if __name__ == "__main__":
    main()