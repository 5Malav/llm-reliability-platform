"""
Replay the golden questions through the running API, so Prometheus and
Grafana see real traffic. Costs about the same as a full eval run (~$0.50).

Run (server must be running):  python -m eval.replay_api
"""
import json
from pathlib import Path

import httpx

rows = [json.loads(l) for l in Path("eval/golden_dataset.jsonl").read_text().splitlines() if l.strip()]

with httpx.Client(base_url="http://localhost:8000", timeout=60) as client:
    for i, r in enumerate(rows, 1):
        resp = client.post("/ask", json={"question": r["question"]})
        if resp.status_code != 200:
            outcome = "ERROR"
        else:
            outcome = "refused" if resp.json()["refused"] else "answered"
        print(f"[{i:>3}/{len(rows)}] {resp.status_code} {outcome:<8} {r['question'][:50]}")