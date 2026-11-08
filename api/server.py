"""
Minimal API server around the RAG pipeline.

Run:  uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from api.rag import FALLBACK_MODEL, MODEL, answer, langfuse
from monitoring.logger import estimate_cost, log_query
from monitoring.metrics import ERRORS, init_metrics, record
from retrieval.keyword_search import keyword_search


@asynccontextmanager
async def lifespan(app):
    # Startup: create every metric label at 0, so the first event shows up (INC-013)
    init_metrics([MODEL, FALLBACK_MODEL])
    # Startup: build the BM25 index now, not on the first user's request
    keyword_search("warmup", top_k=1)
    yield
    # Shutdown: send any traces still waiting in the queue
    langfuse.flush()


app = FastAPI(title="LLM Reliability Platform", lifespan=lifespan)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(body: Question):
    try:
        result = answer(body.question)
    except Exception:
        ERRORS.inc()          # something broke — not a refusal
        raise
    log_query(result)
    record(result, estimate_cost(result["input_tokens"], result["output_tokens"]))
    return result


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)