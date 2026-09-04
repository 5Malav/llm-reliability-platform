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
| Retrieval | Hybrid (BM25 + vector) + reranker + contextual retrieval | Keywords catch exact terms vectors miss |
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
| 3 | Retrieval quality — hybrid + rerank | ⬜ |
| 4–5 | Golden dataset + eval pipeline | ⬜ |
| 6 | Observability (the heart) | ⬜ |
| 7 | Orchestration — LangGraph | ⬜ |
| 8 | Safety — Guardrails | ⬜ |
| 9 | Fine-tuning — RAG vs fine-tune comparison | ⬜ |
| 10 | Production deploy — CI/CD with eval gates | ⬜ |
| 11 | Storytelling — incident log, blog, launch | ⬜ |

## Data Pipeline (Phase 1 — `v1.0`)

811 source .mdx → 792 clean docs → 2,654 chunks → 2,654 embeddings → Postgres


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
question → embed → retrieve top-5 → distance gate → grounded prompt → cited answer
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

### Engineering log

Six incidents were found and fixed across Phases 1–2 — every one caught by cross-checking numbers rather than by an error message. See [`INCIDENTS.md`](./INCIDENTS.md) for root causes, and [`DECISIONS.md`](./DECISIONS.md) for the rationale behind each architectural choice.

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
python ingestion/clean_docs.py
python ingestion/chunk_docs.py
python ingestion/embed_chunks.py
python ingestion/load_to_db.py

# Ask a question
python api/rag.py "how do I set up GitHub authentication?"
```