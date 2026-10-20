"""
Retrieval-only eval: did retrieval find the right content in the top 5?
No LLM calls — nearly free. Tests several BM25 weights.

  normal questions : the expected doc must be in the top 5
  bare tokens      : any top-5 chunk must CONTAIN the token text
                     (a bare token lives in many docs, so one
                      expected file is too strict a test)

Run:  python -m eval.retrieval_eval
"""
import json
from pathlib import Path

import retrieval.hybrid_search as hs

rows = [json.loads(l) for l in Path("eval/golden_dataset.jsonl").read_text().splitlines() if l.strip()]
rows = [r for r in rows if r["answerable"]]


def hit(r):
    chunks = hs.hybrid_search(r["question"])
    is_bare = r["category"] == "exact_token" and not r["question"].endswith("?")
    if is_bare:
        token = r["question"].rstrip("()").lower()
        return any(token in c["text"].lower() for c in chunks)
    want = r["expected_source"].removesuffix(".mdx").replace("/", "__")
    return want in [hs.doc_of(c["chunk_id"]) for c in chunks]


for weight in [0.0, 0.5, 1.0, 1.5, 2.0]:
    hs.BM25_WEIGHT = weight
    results = {}
    for r in rows:
        results.setdefault(r["category"], []).append(hit(r))
    total = sum(sum(v) for v in results.values())
    detail = "  ".join(f"{cat} {sum(v)}/{len(v)}" for cat, v in results.items())
    print(f"BM25_WEIGHT={weight}:  total {total}/{len(rows)}  |  {detail}")