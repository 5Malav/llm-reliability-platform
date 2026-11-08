"""
RAG pipeline: question -> retrieve -> ground -> cited answer.

Every query is traced to Langfuse as one trace:
  rag-query  -> retrieval span  -> llm-call generation (unless gated)
Every answer gets a grounding score: share of claim sentences that carry a source.

Run:  python -m api.rag "how do I set up GitHub auth?"
"""

import sys
import time

from dotenv import load_dotenv

load_dotenv()   # must run BEFORE the Langfuse client is created — it reads keys once

from langfuse import get_client
from litellm import completion

from retrieval.hybrid_search import hybrid_search
from api.prompts import SYSTEM_PROMPT, build_user_message
from monitoring.logger import log_query, COST_PER_1M
from monitoring.quality import grounding

langfuse = get_client()

MODEL = "anthropic/claude-haiku-4-5-20251001"   # DEC-002: Haiku default
TOP_K = 5
MAX_TOKENS = 800

FALLBACK_MODEL = "openai/gpt-4o-mini"    # provider failover
DISTANCE_THRESHOLD = 0.65                # above this = refuse without generating
REFUSAL = "I don't have information about that in the Supabase documentation I have access to."


def is_refusal(text):
    """True only if the response IS the refusal, not a preamble to an answer (INC-006)."""
    return text.startswith(REFUSAL[:40]) and len(text) < len(REFUSAL) + 100


def finish(trace, result):
    """Attach the final outcome to the trace, then return the result unchanged."""
    trace.update(
        output=result["answer"],
        metadata={
            "refused": result["refused"],
            "refusal_reason": result.get("refusal_reason"),
            "hedged": result.get("hedged", False),
            "best_distance": result["best_distance"],
            "best_bm25": result["best_bm25"],
            "model": result.get("model"),
            "grounding_score": result.get("grounding_score"),
            "fake_citations": result.get("fake_citations", 0),
            "retrieval_seconds": result["retrieval_seconds"],
            "llm_seconds": result["llm_seconds"],
            "total_seconds": result["total_seconds"],
        },
    )
    # Grounding as a real Langfuse score, so it can be filtered and charted.
    # Watching the system must never break it, so failures are ignored.
    if result.get("grounding_score") is not None:
        try:
            trace.score_trace(name="grounding", value=float(result["grounding_score"]),
                              data_type="NUMERIC")
        except Exception:
            pass
    return result


def answer(question, top_k=TOP_K):
    """Answer a question from retrieved documentation. Returns a result dict."""
    start = time.time()

    with langfuse.start_as_current_observation(
        as_type="span", name="rag-query", input={"question": question}
    ) as trace:

        # 1. Retrieve — hybrid (vector + BM25, fused, diversity-capped)
        with langfuse.start_as_current_observation(as_type="span", name="retrieval") as span:
            chunks = hybrid_search(question, top_k=top_k)
            span.update(output=[
                {"title": c["title"], "distance": c.get("distance"), "bm25": c.get("bm25_score", 0.0)}
                for c in chunks
            ])
        retrieval_time = time.time() - start

        base = {
            "question": question,
            "sources": [
                {"n": i, "title": c["title"], "url": c["url"], "distance": c.get("distance")}
                for i, c in enumerate(chunks, 1)
            ],
            "best_distance": chunks[0].get("distance") if chunks else None,
            "best_bm25": max((c.get("bm25_score", 0.0) for c in chunks), default=0.0),
            "retrieval_seconds": round(retrieval_time, 3),
            "input_tokens": 0,
            "output_tokens": 0,
            "llm_seconds": 0.0,
            "model": None,
            "grounding_score": None,     # only answers get a score
            "fake_citations": 0,
        }

        # Nothing retrieved at all
        if not chunks:
            return finish(trace, {**base, "answer": REFUSAL, "refused": True,
                                  "refusal_reason": "no_chunks",
                                  "total_seconds": round(time.time() - start, 3)})

        # Retrieval too weak: refuse WITHOUT calling the LLM
        best = chunks[0].get("distance")
        if best is not None and best > DISTANCE_THRESHOLD:
            return finish(trace, {**base, "answer": REFUSAL, "refused": True,
                                  "refusal_reason": "distance_gate",
                                  "total_seconds": round(time.time() - start, 3)})

        # 2. Build the grounded prompt
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(question, chunks)},
        ]

        # 3. Generate — traced as a generation, with provider failover
        llm_start = time.time()
        with langfuse.start_as_current_observation(
            as_type="generation", name="llm-call", model=MODEL, input=messages
        ) as gen:
            used_model = MODEL
            try:
                response = completion(model=MODEL, messages=messages, max_tokens=MAX_TOKENS)
            except Exception as primary_error:
                print(f"  ⚠️  {MODEL} failed ({type(primary_error).__name__}) — falling back to {FALLBACK_MODEL}")
                try:
                    response = completion(model=FALLBACK_MODEL, messages=messages, max_tokens=MAX_TOKENS)
                    used_model = FALLBACK_MODEL
                except Exception as fallback_error:
                    error = f"{type(primary_error).__name__} / {type(fallback_error).__name__}"
                    gen.update(metadata={"error": error})
                    return finish(trace, {**base,
                                          "answer": "Both providers are currently unavailable. Please try again.",
                                          "refused": True, "refusal_reason": "all_providers_failed",
                                          "error": error,
                                          "total_seconds": round(time.time() - start, 3)})

            text = response.choices[0].message.content.strip()
            usage = response.usage
            # Cost uses Haiku prices; a fallback call is cheaper, so this slightly overstates it
            in_cost = usage.prompt_tokens / 1_000_000 * COST_PER_1M["input"]
            out_cost = usage.completion_tokens / 1_000_000 * COST_PER_1M["output"]

            gen.update(
                model=used_model,
                output=text,
                usage_details={"input": usage.prompt_tokens, "output": usage.completion_tokens},
                cost_details={"input": in_cost, "output": out_cost},
            )
        llm_time = time.time() - llm_start

        refused = is_refusal(text)
        hedged = text.startswith(REFUSAL[:40]) and not refused   # INC-006

        # 4. Grounding — only for real answers. For a hedge, drop the refusal
        #    sentence first: it never has a source and would unfairly lower the score.
        quality = {}
        if not refused:
            quality = grounding(text.replace(REFUSAL, ""), len(chunks))

        return finish(trace, {
            **base,
            "answer": text,
            "refused": refused,
            "refusal_reason": "model_refused" if refused else None,
            "hedged": hedged,
            "model": used_model,
            "input_tokens": usage.prompt_tokens,
            "output_tokens": usage.completion_tokens,
            "llm_seconds": round(llm_time, 3),
            "total_seconds": round(time.time() - start, 3),
            "grounding_score": quality.get("score"),
            "fake_citations": quality.get("fake_citations", 0),
        })


def main():
    if len(sys.argv) < 2:
        print('Usage: python -m api.rag "your question"')
        return

    result = answer(sys.argv[1])
    log_query(result)

    print(f"\nQUESTION: {result['question']}")
    print("=" * 70)
    print(f"\n{result['answer']}\n")
    print("=" * 70)
    print("\nSOURCES:")
    for s in result["sources"]:
        link = s["url"] or "(no direct link — documentation fragment)"
        dist = f"{s['distance']:.3f}" if s["distance"] is not None else "  -  "
        print(f"  [{s['n']}] {s['title']}  ({dist})")
        print(f"      {link}")

    best = result["best_distance"]
    print(f"\nbest distance : {best:.4f}" if best is not None else "\nbest distance : n/a")
    print(f"best bm25     : {result['best_bm25']:.2f}")
    print(f"tokens        : {result['input_tokens']} in / {result['output_tokens']} out")
    print(f"timing        : retrieval {result['retrieval_seconds']}s | "
          f"llm {result['llm_seconds']}s | total {result['total_seconds']}s")
    print(f"refused       : {result['refused']}  ({result.get('refusal_reason') or 'n/a'})")
    if result.get("hedged"):
        print("⚠️  HEDGED     : refusal string present but an answer followed (INC-006)")
    g = result.get("grounding_score")
    print(f"grounding     : {g:.0%} of claims sourced" if g is not None else "grounding     : n/a")
    if result.get("fake_citations"):
        print(f"🚩 FAKE CITES : {result['fake_citations']} citation(s) point at sources that don't exist")
    print(f"model         : {result.get('model') or 'none (gated)'}")

    langfuse.flush()   # send the trace before the script exits


if __name__ == "__main__":
    main()