"""
Check the golden dataset against the real corpus.

Verifies that every expected_source actually exists as a file, and
reports category counts. Run this before running the full eval.

Run:  python -m eval.validate_dataset
"""

import json
from collections import Counter
from pathlib import Path

DATASET = Path("eval/golden_dataset.jsonl")
CORPUS = Path("ingestion/data/raw/supabase-docs")


def main():
    rows = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]

    print(f"Questions: {len(rows)}\n")

    print("BY CATEGORY")
    for cat, n in Counter(r["category"] for r in rows).most_common():
        print(f"  {cat:<16} {n}")

    answerable = [r for r in rows if r["answerable"]]
    print(f"\nanswerable:   {len(answerable)}")
    print(f"unanswerable: {len(rows) - len(answerable)}\n")

    # Check every expected_source exists
    missing = []
    for r in answerable:
        if not (CORPUS / r["expected_source"]).exists():
            missing.append(r)

    print(f"SOURCE PATHS: {len(answerable) - len(missing)} valid, {len(missing)} missing")

    if missing:
        print("\nMISSING — these need fixing:")
        for r in missing:
            print(f"  id {r['id']:>3}  {r['expected_source']}")
            print(f"           Q: {r['question'][:65]}")


if __name__ == "__main__":
    main()