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
| 1 | Document ingestion — clean, chunk, embed, store | 🔄 in progress |
| 2 | Basic RAG — retrieve + cited answers | ⬜ |
| 3 | Retrieval quality — hybrid + rerank | ⬜ |
| 4–5 | Golden dataset + eval pipeline | ⬜ |
| 6 | Observability (the heart) | ⬜ |
| 7 | Orchestration — LangGraph | ⬜ |
| 8 | Safety — Guardrails | ⬜ |
| 9 | Fine-tuning — RAG vs fine-tune comparison | ⬜ |
| 10 | Production deploy — CI/CD with eval gates | ⬜ |
| 11 | Storytelling — incident log, blog, launch | ⬜ |

## Data Pipeline (Phase 1)


- **Source:** `apps/docs/content` from the [supabase/supabase](https://github.com/supabase/supabase) monorepo, pinned to commit `5b68af17` — the corpus is reproducible, not scraped
- **Cleaning:** custom MDX preprocessor — strips component tags, protects code blocks, extracts metadata, filters nav-only pages
- **Chunking:** 500-token sliding window, 75-token (15%) overlap, 100-token floor for trailing slices
- **Metadata:** every chunk carries title, source path, doc type, and a resolvable docs URL for citation
- **Embeddings:** `text-embedding-3-small` (1536d), batched 100/call, resumable, ~$0.023 for the full corpus
- **Storage:** Postgres 16 + pgvector in Docker; idempotent upsert on `chunk_id`

### Retrieval — measured behaviour

| Query | Top result | Distance |
|---|---|---|
| "how do I set up GitHub authentication?" | Login with GitHub | **0.38** |
| "what are the API rate limits?" | API rate limits | **0.39** |
| "why am I getting row level security errors?" | Row Level Security | **0.48** |
| "how do I make a pizza?" *(out of scope)* | — | **0.72** |

Answerable questions retrieve at 0.38–0.51; out-of-scope questions at 0.72+. That separation is an externally-computed confidence signal — the basis for calibrated refusal in later phases.

### Engineering log

Five incidents were found and fixed during Phase 1 — every one caught by cross-checking numbers rather than by an error message. See [`INCIDENTS.md`](./INCIDENTS.md).

## Setup

```bash
# Clone and enter
git clone https://github.com/5Malav/llm-reliability-platform.git
cd llm-reliability-platform

# Python 3.11.9 (pinned via .python-version)
python3 -m venv venv
source venv/bin/activate

# Configure secrets
cp .env.example .env
# fill in your ANTHROPIC_API_KEY and OPENAI_API_KEY
```