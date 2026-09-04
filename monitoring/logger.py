"""
Query logging — one JSON line per query.

Writes the metrics we already capture to a JSONL file. This is the raw
material for Phase 6 dashboards (cost, latency, refusal rate).

Format: JSONL (one JSON object per line) — appendable, streamable,
easy to load into pandas or a dashboard later.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path("monitoring/query_log.jsonl")

# text-embedding-3-small + claude-haiku-4-5 (USD per 1M tokens)
COST_PER_1M = {"input": 1.00, "output": 5.00}


def estimate_cost(input_tokens, output_tokens):
    """Rough USD cost for one query."""
    return round(
        (input_tokens / 1_000_000) * COST_PER_1M["input"]
        + (output_tokens / 1_000_000) * COST_PER_1M["output"],
        6,
    )


def log_query(result):
    """Append one query's metrics to the log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": result["question"],
        "refused": result.get("refused", False),
        "refusal_reason": result.get("refusal_reason"),
        "hedged": result.get("hedged", False),
        "best_distance": result.get("best_distance"),
        "model": result.get("model"),
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "cost_usd": estimate_cost(
            result.get("input_tokens", 0), result.get("output_tokens", 0)
        ),
        "retrieval_seconds": result.get("retrieval_seconds"),
        "llm_seconds": result.get("llm_seconds"),
        "total_seconds": result.get("total_seconds"),
        "num_sources": len(result.get("sources", [])),
    }

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return entry