"""
Run the golden dataset through the RAG system and save the results.

This is the harness. It does NOT score anything — scoring is Phase 5.
It records what the system did for every question so results can be
compared across changes.

Run:  python -m eval.run_golden            (all 120, ~$0.40)
      python -m eval.run_golden --limit 10 (first 10, for testing)
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from api.rag import answer

DATASET = Path("eval/golden_dataset.jsonl")
RESULTS_DIR = Path("eval/results")


def source_matched(result, expected_source):
    """True if the expected document appears anywhere in the retrieved sources."""
    if not expected_source:
        return None
    # source_path isn't carried through rag.py's output, so match on the
    # document stem instead (e.g. 'auth-github' from the expected path)
    stem = Path(expected_source).stem.lower()
    return any(stem in (s["title"] or "").lower().replace(" ", "-") or
               stem in (s["url"] or "").lower()
               for s in result["sources"])


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    rows = [json.loads(l) for l in DATASET.read_text().splitlines() if l.strip()]
    if limit:
        rows = rows[:limit]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_file = RESULTS_DIR / f"run-{stamp}.jsonl"

    print(f"Running {len(rows)} questions...\n")
    start = time.time()
    total_cost = 0.0

    with out_file.open("w", encoding="utf-8") as f:
        for i, row in enumerate(rows, 1):
            try:
                result = answer(row["question"])
                error = None
            except Exception as e:
                result = None
                error = f"{type(e).__name__}: {e}"

            if result:
                cost = (result["input_tokens"] / 1_000_000) * 1.00 + \
                       (result["output_tokens"] / 1_000_000) * 5.00
                total_cost += cost

                record = {
                    "id": row["id"],
                    "question": row["question"],
                    "category": row["category"],
                    "answerable": row["answerable"],
                    "expected_source": row["expected_source"],
                    "answer": result["answer"],
                    "refused": result["refused"],
                    "refusal_reason": result.get("refusal_reason"),
                    "hedged": result.get("hedged", False),
                    "best_distance": result["best_distance"],
                    "sources": result["sources"],
                    "source_matched": source_matched(result, row["expected_source"]),
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "cost_usd": round(cost, 6),
                    "retrieval_seconds": result["retrieval_seconds"],
                    "llm_seconds": result["llm_seconds"],
                    "total_seconds": result["total_seconds"],
                    "error": None,
                }
            else:
                record = {**row, "error": error}

            f.write(json.dumps(record) + "\n")
            f.flush()   # crash-safe: results survive an interruption

            mark = "REFUSED" if (result and result["refused"]) else "answered"
            if error:
                mark = "ERROR"
            print(f"  [{i:>3}/{len(rows)}] {row['category']:<14} {mark:<9} {row['question'][:45]}")

    elapsed = time.time() - start
    print(f"\n--- Run complete ---")
    print(f"Questions:  {len(rows)}")
    print(f"Cost:       ${total_cost:.4f}")
    print(f"Time:       {elapsed/60:.1f} min")
    print(f"Saved to:   {out_file}")


if __name__ == "__main__":
    main()