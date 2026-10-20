"""Summarize the latest golden-dataset run (end-to-end behaviour only).
Retrieval accuracy is measured separately by eval/retrieval_eval.py."""
import json
from pathlib import Path

path = sorted(Path("eval/results").glob("run-*.jsonl"))[-1]
rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def declined(r):
    """A hedge IS a refusal — the model declined, then explained itself."""
    return r["refused"] or r.get("hedged", False)


# Bare tokens aren't questions, so they're judged on retrieval only
# (retrieval_eval.py). Here we score real questions end to end.
end_to_end = [r for r in rows if r["category"] != "exact_token"]
answerable = [r for r in end_to_end if r["answerable"]]
unanswerable = [r for r in end_to_end if not r["answerable"]]

wrong_refuse = [r for r in answerable if declined(r)]
wrong_answer = [r for r in unanswerable if not declined(r)]
hedges = [r for r in end_to_end if r.get("hedged")]

print(f"{path.name}  ({len(rows)} questions)\n")
print(f"answerable    : {len(answerable)-len(wrong_refuse)}/{len(answerable)} answered correctly")
print(f"unanswerable  : {len(unanswerable)-len(wrong_answer)}/{len(unanswerable)} declined correctly")
print(f"hedge rate    : {len(hedges)}/{len(end_to_end)}")
print(f"cost          : ${sum(r.get('cost_usd',0) for r in rows):.4f}")

print("\nWRONGLY REFUSED")
for r in wrong_refuse:
    print(f"  [{r['id']}] {r['question'][:55]}")

print("\nWRONGLY ANSWERED (hallucination risk)")
for r in wrong_answer:
    print(f"  [{r['id']}] {r['question'][:55]}")