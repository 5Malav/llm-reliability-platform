# LLM Reliability Platform

> A production RAG system over Supabase's docs where the **observability layer is the product** and the chatbot is just the workload under management.

## The Problem

LLM systems fail differently from normal software. A crashed server announces itself — but a hallucinated answer looks identical to a correct one: same confident tone, same speed, zero errors in the logs. Cost drifts upward token by token with no alarm. Latency degrades somewhere across retrieval, reranking, and generation, with no single place to look.

Most teams ship the chatbot first and bolt on logging later, so they discover failures from angry users. **This project inverts that.** The observability layer — hallucination rate, cost per query, latency breakdown, retrieval quality, and eval gates that block bad deploys — is built as the product. A RAG assistant over Supabase's documentation is simply the workload being monitored.

## Why This Project

This is the LLM-reliability counterpart to a classical MLOps pipeline: proving that production language-model systems can be kept **alive, observable, and trustworthy** — not just demoed once and abandoned.

## Target Architecture

| Layer | Choice | Why |
|-------|--------|-----|
| LLM access | Claude (Haiku default) + OpenAI fallback via LiteLLM | Multi-provider = no single point of failure |
| Vector store | Postgres + pgvector | One boring, proven DB — fewer moving parts |
| Retrieval | Hybrid (BM25 + vector) with weighted RRF | Keywords catch exact terms vectors miss |
| Orchestration | LangGraph | Explicit, debuggable state machine |
| Observability | OpenTelemetry → Langfuse + Prometheus/Grafana | Instrument once, swap vendors freely |
| Evaluation | RAGAS + DeepEval + hand-built golden dataset | Every change is measurable |
| Safety | Guardrails AI | Injection + PII filtering at input and output |
| Infra | FastAPI · Docker · Cloud Run · GitHub Actions · Terraform | Reused, battle-tested stack |

## Progress

Built in public, one phase at a time. Each phase ships a version tag.

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Foundation — repo, env, funded keys, smoke test | ✅ `v0.0` |
| 1 | Document ingestion — clean, chunk, embed, store | ✅ `v1.0` |
| 2 | Basic RAG — retrieve + cited answers | ✅ `v1.1` |
| 3 | Retrieval quality — hybrid search + diversity | ✅ `v1.2` |
| 4 | Golden dataset — hand-written Q/A pairs | ⬜ |
| 5 | Eval pipeline — RAGAS, DeepEval, baselines | ⬜ |
| 6 | Observability (the heart) | ⬜ |
| 7 | Orchestration — LangGraph | ⬜ |
| 8 | Safety — Guardrails | ⬜ |
| 9 | Fine-tuning — RAG vs fine-tune comparison | ⬜ |
| 10 | Production deploy — CI/CD with eval gates | ⬜ |
| 11 | Storytelling — incident log, blog, launch | ⬜ |

## Data Pipeline (Phase 1 — `v1.0`)

```
811 source .mdx → 792 clean docs → 2,654 chunks → 2,654 embeddings → Postgres
```

- **Source:** `apps/docs/content` from the [supabase/supabase](https://github.com/supabase/supabase) monorepo, pinned to commit `5b68af17` — the corpus is reproducible, not scraped
- **Cleaning:** custom MDX preprocessor — strips component tags, protects code blocks, extracts metadata, filters nav-only pages
- **Chunking:** 500-token sliding window, 75-token (15%) overlap, 100-token floor for trailing slices
- **Metadata:** every chunk carries title, source path, doc type, and a resolvable docs URL for citation
- **Embeddings:** `text-embedding-3-small` (1536d), batched 100/call, resumable, ~$0.023 for the full corpus
- **Storage:** Postgres 16 + pgvector in Docker; idempotent upsert on `chunk_id`

### Retrieval — measured behaviour

Across a test set of 8 queries, retrieval distance separates answerable from out-of-scope questions cleanly:

| Query | Distance | Outcome |
|---|---|---|
| "how do I deploy an edge function?" | **0.28** | answered |
| "how do I set up GitHub authentication?" | **0.38** | answered |
| "how do I upload a file to storage?" | **0.39** | answered |
| "what is Row Level Security?" | **0.40** | answered |
| "how do I create a database function?" | **0.41** | answered |
| "why am I getting row level security errors?" | **0.48** | answered |
| "how do I make a pizza?" *(out of scope)* | **0.72** | refused |
| "what is the capital of France?" *(out of scope)* | **0.83** | refused |

Answerable questions retrieve at **0.28–0.48**; out-of-scope questions at **0.72+**. A ~0.25 gap with no overlap. That separation is an externally-computed confidence signal — not the model's self-reported confidence — and it is what the refusal gate acts on.

## RAG Pipeline (Phase 2 — `v1.1`)

Retrieved chunks are grounded into cited answers, with refusal treated as correct behaviour rather than failure.

```
question → retrieve top-5 → distance gate → grounded prompt → cited answer
                                  ↓ (> 0.65)
                               refuse, zero cost
```

- **Grounding:** the system prompt permits answers only from retrieved context, requires a citation on every claim, and specifies an exact refusal sentence — a fixed string is machine-detectable, which makes refusal rate a metric rather than a hope
- **Calibrated refusal:** when the best retrieval distance exceeds 0.65, the query is refused **before the LLM is called** — a cheap deterministic signal gating an expensive stochastic one
- **Provider failover:** all calls route through LiteLLM; a primary-provider failure falls back automatically. A single provider is a single point of failure
- **Telemetry from day one:** every query logs cost, token counts, retrieval-vs-generation latency split, best distance, and refusal reason to JSONL

### Measured performance

| Metric | Value |
|---|---|
| Cost per answered query | **$0.0047** (~$4.70 / 1,000 queries) |
| Cost per refused query | **$0.0000** (gated before generation) |
| Latency — answered | **4.8s** avg (retrieval 0.7–0.9s, generation 3.6–5.2s) |
| Latency — refused | **0.6–0.9s** (~5× faster) |

Generation dominates latency, not retrieval — a distinction only visible because the split is logged per query rather than as a single total.

### Refusal categories

Refusals are labelled by cause, because each demands a different fix:

| Reason | Meaning |
|---|---|
| `distance_gate` | Retrieval too weak — refused before generation |
| `model_refused` | Retrieval acceptable, but the model judged the context insufficient |
| `no_chunks` | Search returned nothing |
| `all_providers_failed` | Infrastructure failure, not a knowledge gap |

A `hedged` flag additionally catches responses that emit the refusal string and then answer anyway — a contradiction that would otherwise corrupt the refusal metric ([INC-006](./INCIDENTS.md)).

## Retrieval Quality (Phase 3 — `v1.2`)

Semantic search alone has a specific blind spot: it blurs exact tokens. Error codes, function names and config keys carry little learned meaning, so they map to a generic "technical identifier" region where every error code looks alike.

```
question ─┬─ vector search (top 10) ─┐
          └─ BM25 search   (top 10) ─┴─ weighted RRF → diversity cap → top 5
```

- **Hybrid retrieval:** vector search handles paraphrase and intent; BM25 handles exact tokens. They fail in opposite directions, so fusing them covers both
- **Weighted RRF:** rankings are fused by position, not score — cosine distance and BM25 scores aren't comparable, and normalising means choosing an arbitrary mapping that biases one retriever. Vector is weighted 1.0 as the primary retriever; BM25 0.5 as a specialist that rescues exact-token queries without overriding good semantic results
- **Diversity cap:** at most 2 chunks per document. Queries routinely returned 3–4 chunks from one source, so five slots carried a single document's worth of evidence

### Measured: the exact-token case

Searching the error code `PGRST116`:

| Retriever | Behaviour |
|---|---|
| BM25 | Correct doc scored **7.47**; every other chunk scored **0.00** — one document contains that token, so it is certain |
| Vector | Correct doc first at **0.539**, but geospatial-routing docs at **0.642** and a *different* error code (PGRST106) at **0.652** — only 0.11 separating right from wrong |
| Hybrid | Correct doc first, at **2× the score** of anything else, because both retrievers agreed |

Before Phase 3 this query produced a generic answer. It now answers: *"PGRST116 is a 406 error that occurs when more than 1 or no items are returned when requesting a singular response."*

### Built, measured, and not shipped

Two further changes were implemented and then deliberately left out of the pipeline:

| Change | Result | Decision |
|---|---|---|
| Cross-encoder reranker | Ranked the PGRST106 page above the page containing PGRST116; added ~5s per query against a 4.8s baseline | Not shipped — [DEC-014](./DECISIONS.md) |
| Document-type boost for problem queries | Promoted a chunk both retrievers ranked poorly (vector #10, BM25 #7) to first, pushing the canonical guide out of the top five | Built but disabled — [DEC-015](./DECISIONS.md) |

**Two of four retrieval changes this phase made results worse.** They were caught by checking — but the checking was eyeballing two or three queries per change, which is not measurement. The two changes with clear, repeatable wins shipped; the rest are parked behind config constants until the golden dataset can decide with numbers.

This is the argument for Phase 4: you cannot improve what you cannot measure, and an unmeasured "improvement" is how a system quietly gets worse.

### Engineering log

Seven incidents and three observations are recorded across Phases 1–3 — every one surfaced by cross-checking numbers rather than by an error message. See [`INCIDENTS.md`](./INCIDENTS.md) for root causes and [`DECISIONS.md`](./DECISIONS.md) for the rationale behind each architectural choice.

## Setup

```bash
# Clone and enter
git clone https://github.com/5Malav/llm-reliability-platform.git
cd llm-reliability-platform

# Python 3.11.9 (pinned via .python-version)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure secrets
cp .env.example .env
# fill in ANTHROPIC_API_KEY, OPENAI_API_KEY, DATABASE_URL

# Start the vector store
docker compose up -d
docker compose exec -T db psql -U postgres -d llm_reliability < ingestion/schema.sql

# Build the corpus
python -m ingestion.clean_docs
python -m ingestion.chunk_docs
python -m ingestion.embed_chunks
python -m ingestion.load_to_db

# Ask a question
python -m api.rag "how do I set up GitHub authentication?"

# Or inspect retrieval on its own
python -m retrieval.hybrid_search "PGRST116"
```