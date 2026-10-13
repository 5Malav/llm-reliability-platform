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
| Evaluation | Hand-built golden dataset + RAGAS + DeepEval | Every change is measurable |
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
| 4 | Golden dataset — 120 hand-written questions | ✅ `v1.3` |
| 5 | Eval pipeline — RAGAS, DeepEval, scoring | ⬜ |
| 6 | Observability (the heart) | ⬜ |
| 7 | Orchestration — LangGraph | ⬜ |
| 8 | Safety — Guardrails | ⬜ |
| 9 | Fine-tuning — RAG vs fine-tune comparison | ⬜ |
| 10 | Production deploy — CI/CD with eval gates | ⬜ |
| 11 | Storytelling — incident log, blog, launch | ⬜ |

## Current baseline

Measured against 120 hand-written questions. These are the honest numbers, not the aspirational ones.

| Metric | Result |
|---|---|
| Answerable questions correctly answered | **78 / 85** (92%) |
| Answerable questions **wrongly refused** | **7 / 85** (8%) |
| Unanswerable questions correctly refused | **17 / 35** (49%) |
| Unanswerable questions **wrongly answered** | **18 / 35** (51%) |
| Cost per question | **$0.0039** |
| Full 120-question eval run | **$0.47 · 7.8 min** |

The project's headline claim is calibrated refusal. Measured at baseline, refusal is correct **49%** of the time. Phase 5 exists to move that number — and to prove the movement rather than assert it.

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

## RAG Pipeline (Phase 2 — `v1.1`)

Retrieved chunks are grounded into cited answers, with refusal treated as correct behaviour rather than failure.

```
question → retrieve top-5 → distance gate → grounded prompt → cited answer
                                  |
                                  +-- distance > 0.65: refuse, zero cost
```

- **Grounding:** the system prompt permits answers only from retrieved context, requires a citation on every claim, and specifies an exact refusal sentence — a fixed string is machine-detectable, which makes refusal rate a metric rather than a hope
- **Calibrated refusal:** when the best retrieval distance exceeds 0.65, the query is refused **before the LLM is called** — a cheap deterministic signal gating an expensive stochastic one
- **Provider failover:** all calls route through LiteLLM; a primary-provider failure falls back automatically. A single provider is a single point of failure
- **Telemetry from day one:** every query logs cost, token counts, retrieval-vs-generation latency split, best distance, and refusal reason to JSONL

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
question --+-- vector search (top 10) --+
           |                            +-- weighted RRF -> diversity cap -> top 5
           +-- BM25 search   (top 10) --+
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

Two changes were implemented and then deliberately left out of the pipeline:

| Change | Result | Decision |
|---|---|---|
| Cross-encoder reranker | Ranked the PGRST106 page above the page containing PGRST116; added ~5s per query against a 4.8s baseline | Not shipped — [DEC-014](./DECISIONS.md) |
| Document-type boost for problem queries | Promoted a chunk both retrievers ranked poorly (vector #10, BM25 #7) to first, pushing the canonical guide out of the top five | Built but disabled — [DEC-015](./DECISIONS.md) |

**Two of four retrieval changes this phase made results worse.** They were caught by checking — but the checking was eyeballing two or three queries per change, which is not measurement. The two changes with clear, repeatable wins shipped; the rest are parked behind config constants until the golden dataset can decide with numbers.

## Golden Dataset (Phase 4 — `v1.3`)

120 question/answer pairs, written by hand against the real corpus. No LLM generation — an auto-generated set only tests whether the system agrees with another model.

| Category | Count | What it tests |
|---|---:|---|
| `simple_lookup` | 40 | Basic retrieval and citation |
| `multi_step` | 25 | Whether multiple relevant chunks are assembled correctly |
| `exact_token` | 20 | Bare strings (`aal2`, `42501`, `maybeSingle()`) — hybrid/BM25 specifically |
| `unanswerable` | 35 | Calibrated refusal — the project's core claim |

Unanswerable questions are 29% of the set deliberately. A set that is 95% answerable can score well while refusing nothing correctly.

Exact-token questions are written as **bare strings**, not as "what does X do?" — natural-language phrasing is answered by vector search regardless, so it would not test the thing BM25 exists for.

### What the first run found

The baseline run surfaced two failures in eight minutes that weeks of spot-checking had missed.

**1. Two features in conflict.** All seven wrongly-refused questions were bare-token `exact_token` queries. The 0.65 distance gate was tuned on sentence-shaped questions (0.28–0.48 cosine distance); a bare token carries no sentence context, so it lands further out and is gated before the model ever sees it. BM25 had already found the correct chunk — the gate didn't consider that.

**2. Refusal is weaker than claimed.** 51% of unanswerable questions were answered rather than refused. The worst cluster was cross-product questions about Firebase — the corpus discusses third-party auth, so the model finds adjacent content and speaks from it.

### Known weakness in the dataset itself

Most unanswerable questions use absolute phrasing — "exact", "guaranteed", "every", "confidential" — which makes them *easy* refusals. The hard ones are mild and ordinary, the kind a developer would type without suspecting the answer isn't documented. One mild question in the set ("what is Supabase's uptime SLA for the Free plan?") produced a **hedge** rather than a clean refusal. A future revision should weight toward mild refusals, which is where hallucination actually occurs.

### Engineering log

Seven incidents and three observations are recorded across Phases 1–4 — every one surfaced by cross-checking numbers rather than by an error message. See [`INCIDENTS.md`](./INCIDENTS.md) for root causes and [`DECISIONS.md`](./DECISIONS.md) for the rationale behind each architectural choice.

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

# Inspect retrieval on its own
python -m retrieval.hybrid_search "PGRST116"

# Run the evaluation suite
python -m eval.validate_dataset          # check dataset integrity
python -m eval.run_golden --limit 10     # smoke test (~$0.04)
python -m eval.run_golden                # full run (~$0.47, 8 min)
python -m eval.summarize                 # read the results
```