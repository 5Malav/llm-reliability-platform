"""
CI eval gate: run the retrieval eval ONCE, with the settings in the code,
and fail (exit code 1) if quality drops below the agreed thresholds.

Thresholds sit just below the measured baseline (70/85, 20/20) to allow
for small run-to-run wobble in query embeddings (OBS-010), while still
catching real regressions: BM25_WEIGHT=0 scores 63/85 and 16/20.

Run:  python -m eval.gate
"""
import sys

from eval.retrieval_eval import score, summary

MIN_TOTAL = 68         # baseline 70/85
MIN_EXACT_TOKEN = 19   # baseline 20/20


def main():
    results = score()
    print(summary(results))

    total = sum(sum(v) for v in results.values())
    tokens = sum(results.get("exact_token", []))

    failures = []
    if total < MIN_TOTAL:
        failures.append(f"total {total} < {MIN_TOTAL}")
    if tokens < MIN_EXACT_TOKEN:
        failures.append(f"exact_token {tokens} < {MIN_EXACT_TOKEN}")

    if failures:
        print("GATE FAILED: " + "; ".join(failures))
        sys.exit(1)
    print(f"GATE PASSED (need total >= {MIN_TOTAL}, exact_token >= {MIN_EXACT_TOKEN})")


if __name__ == "__main__":
    main()