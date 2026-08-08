# LLM Reliability Platform

> A production RAG system over Supabase's docs where the **observability layer is the product** and the chatbot is just the workload under management.

## The Problem

LLM systems fail differently from normal software. A crashed server announces itself — but a hallucinated answer looks identical to a correct one: same confident tone, same speed, zero errors in the logs. Cost drifts upward token by token with no alarm. Latency degrades somewhere across retrieval, reranking, and generation, with no single place to look.

Most teams ship the chatbot first and bolt on logging later, so they discover failures from angry users. **This project inverts that.** The observability layer — hallucination rate, cost per query, latency breakdown, retrieval quality, and eval gates that block bad deploys — is built as the product. A RAG assistant over Supabase's documentation is simply the workload being monitored.

## Why This Project

This is the LLM-reliability counterpart to a classical MLOps pipeline: proving that production language-model systems can be kept **alive, observable, and trustworthy** — not just demoed once and abandoned.

## Architecture (at a glance)

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

## Status

🚧 **In active development** — building in public, one phase at a time.

See [`docs/`](./docs) for build notes and [`DECISIONS.md`](./DECISIONS.md) for the engineering rationale behind each choice.

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