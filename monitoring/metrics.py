"""
Prometheus metrics for the RAG API.

Labels are kept to a small, fixed set (outcome, token type, model). Never label
by question text — every unique label value creates a new time series.
"""

from prometheus_client import Counter, Histogram

# Our LLM calls take 5-9s, so buckets need detail above the 10s default limit
LATENCY_BUCKETS = (0.25, 0.5, 1, 2, 3, 5, 8, 13, 20, 30)

# Grounding is a 0-1 score, so buckets cover that range
GROUNDING_BUCKETS = (0.25, 0.5, 0.75, 0.9, 1.0)

REQUESTS = Counter("rag_requests_total", "Questions handled, by outcome", ["outcome"])
ERRORS = Counter("rag_errors_total", "Unexpected errors while handling a question")
COST = Counter("rag_cost_usd_total", "Estimated LLM spend in USD")
TOKENS = Counter("rag_tokens_total", "LLM tokens used", ["type"])
FAKE_CITATIONS = Counter("rag_fake_citations_total", "Citations pointing at sources that don't exist")
LLM_CALLS = Counter("rag_llm_calls_total", "Answers generated, by the model that produced them", ["model"])

RETRIEVAL_SECONDS = Histogram("rag_retrieval_seconds", "Retrieval latency", buckets=LATENCY_BUCKETS)
LLM_SECONDS = Histogram("rag_llm_seconds", "LLM latency, only when the LLM was called", buckets=LATENCY_BUCKETS)
TOTAL_SECONDS = Histogram("rag_total_seconds", "End-to-end latency", buckets=LATENCY_BUCKETS)
GROUNDING = Histogram("rag_grounding_score", "Share of claim sentences carrying a source (answers only)",
                      buckets=GROUNDING_BUCKETS)


# Every label value we know about, created at 0 on startup.
# Prometheus measures CHANGE: a counter that first appears already at 1 shows
# no increase, so the very first fallback, error type or outcome would be
# invisible on the dashboard (INC-013).
OUTCOMES = ("answered", "hedged", "distance_gate", "model_refused", "no_chunks", "all_providers_failed")


def init_metrics(models):
    """Create every known label at 0, so the first real event counts as a change."""
    for outcome in OUTCOMES:
        REQUESTS.labels(outcome=outcome)
    for kind in ("input", "output"):
        TOKENS.labels(type=kind)
    for model in models:
        LLM_CALLS.labels(model=model)


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
    if result.get("model"):                       # only when an LLM actually answered
        LLM_CALLS.labels(model=result["model"]).inc()
    if result.get("grounding_score") is not None:
        GROUNDING.observe(result["grounding_score"])
        FAKE_CITATIONS.inc(result.get("fake_citations", 0))