"""
Prometheus metrics for the RAG API.

Labels are kept to a small, fixed set (outcome, token type). Never label by
question text — every unique label value creates a new time series.
"""

from prometheus_client import Counter, Histogram

# Our LLM calls take 5-9s, so buckets need detail above the 10s default limit
LATENCY_BUCKETS = (0.25, 0.5, 1, 2, 3, 5, 8, 13, 20, 30)

REQUESTS = Counter("rag_requests_total", "Questions handled, by outcome", ["outcome"])
ERRORS = Counter("rag_errors_total", "Unexpected errors while handling a question")
COST = Counter("rag_cost_usd_total", "Estimated LLM spend in USD")
TOKENS = Counter("rag_tokens_total", "LLM tokens used", ["type"])

RETRIEVAL_SECONDS = Histogram("rag_retrieval_seconds", "Retrieval latency", buckets=LATENCY_BUCKETS)
LLM_SECONDS = Histogram("rag_llm_seconds", "LLM latency, only when the LLM was called", buckets=LATENCY_BUCKETS)
TOTAL_SECONDS = Histogram("rag_total_seconds", "End-to-end latency", buckets=LATENCY_BUCKETS)


def outcome_of(result):
    """One word describing how a question ended."""
    if result["refused"]:
        return result.get("refusal_reason") or "refused"
    if result.get("hedged"):
        return "hedged"
    return "answered"


def record(result, cost_usd):
    """Update every metric from one finished question."""
    REQUESTS.labels(outcome=outcome_of(result)).inc()
    COST.inc(cost_usd)
    TOKENS.labels(type="input").inc(result["input_tokens"])
    TOKENS.labels(type="output").inc(result["output_tokens"])
    RETRIEVAL_SECONDS.observe(result["retrieval_seconds"])
    if result["llm_seconds"]:
        LLM_SECONDS.observe(result["llm_seconds"])
    TOTAL_SECONDS.observe(result["total_seconds"])