"""Summarize the latest golden-dataset run."""
import json
from pathlib import Path

path = sorted(Path("eval/results").glob("run-*.jsonl"))[-1]
rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

wrong_refuse = [r for r in rows if r["answerable"] and r["refused"]]
wrong_answer = [r for r in rows if not r["answerable"] and not r["refused"]]

print(f"{path.name}  ({len(rows)} questions)")
print(f"wrongly refused : {len(wrong_refuse)}")
print(f"wrongly answered: {len(wrong_answer)}")
print(f"cost            : ${sum(r.get('cost_usd',0) for r in rows):.4f}")

print("\nWRONGLY REFUSED")
for r in wrong_refuse:
    print(f"  [{r['id']}] {r['question'][:50]}")

print("\nWRONGLY ANSWERED")
for r in wrong_answer:
    print(f"  [{r['id']}] {r['question'][:50]}")