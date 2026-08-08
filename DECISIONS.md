# Engineering Decisions

A running log of architectural decisions, the alternatives considered, and the reasoning. Each entry is a defensible choice, not a default.

---

## DEC-001 — SHA-pinned document corpus (not live scraping)

**Decision:** Pull Supabase docs from their public source repository, pinned to a specific commit SHA. Pull GitHub issues via the API. Do **not** scrape rendered HTML.

**Rejected alternative:** Scraping the live docs website.

**Why:** A SHA-pinned corpus is reproducible — anyone can rebuild the exact vector store from the exact source. Scraping is fragile (breaks when the site's HTML changes) and unreproducible (the corpus silently drifts as the site updates). This is DVC-style thinking applied to documents: the data source is versioned, not a moving target.

**Trade-off:** When Supabase ships new docs, I must deliberately re-pin and re-index — the corpus doesn't auto-update. That's a feature: re-indexing becomes a controlled, observable event, not a silent change.

---

## DEC-002 — Model & cost policy: Haiku-default, Batch-gated evals

**Decision:** Claude Haiku 4.5 is the default model everywhere (dev loops, smoke tests, LLM-as-judge). Sonnet 4.6 is used only where evals prove the quality gain justifies the cost. Full golden-eval runs happen only at phase gates, via the Batch API. Daily iteration uses a ~20-question smoke set.

**Rejected alternative:** Sonnet-by-default for quality; running the full eval set on every change.

**Why:** Haiku is ~5× cheaper than Sonnet at near-comparable quality for most tasks. The real budget killer is eval runs (150 questions × generation × multiple judge calls). Restricting full evals to phase gates and routing them through the Batch API (50% discount) keeps the entire project under a ~$20–30/month budget. Cost-per-query is itself a monitored metric — cost discipline is part of the product, not a constraint on it.

**Trade-off:** The ~20-question smoke set gives faster but less complete signal during iteration. Acceptable — full signal is available on demand at gates.