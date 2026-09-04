"""
RAG pipeline: question -> retrieve -> ground -> cited answer.

Run:  python api/rag.py "how do I set up GitHub auth?"
"""

import sys
import time

from dotenv import load_dotenv
from litellm import completion

from retrieval.search import search
from api.prompts import SYSTEM_PROMPT, build_user_message
from monitoring.logger import log_query

load_dotenv()

MODEL = "anthropic/claude-haiku-4-5-20251001"   # DEC-002: Haiku default
TOP_K = 5
MAX_TOKENS = 800

FALLBACK_MODEL = "openai/gpt-4o-mini"    # provider failover
DISTANCE_THRESHOLD = 0.65                # above this = refuse without generating
REFUSAL = "I don't have information about that in the Supabase documentation I have access to."


def is_refusal(text):
    """True only if the response IS the refusal, not a preamble to an answer.

    The model sometimes emits the refusal string and then answers anyway,
    which would log as 'refused' while the user received a full answer (INC-006).
    A genuine refusal is short.
    """
    return text.startswith(REFUSAL[:40]) and len(text) < len(REFUSAL) + 100


def answer(question, top_k=TOP_K):
    """Answer a question from retrieved documentation. Returns a result dict."""
    start = time.time()

    # 1. Retrieve
    chunks = search(question, top_k=top_k)
    retrieval_time = time.time() - start

    base = {
        "question": question,
        "sources": [
            {"n": i, "title": c["title"], "url": c["url"], "distance": c["distance"]}
            for i, c in enumerate(chunks, 1)
        ],
        "best_distance": chunks[0]["distance"] if chunks else None,
        "retrieval_seconds": round(retrieval_time, 3),
        "input_tokens": 0,
        "output_tokens": 0,
        "llm_seconds": 0.0,
        "model": None,
    }

    # 4.1 — Nothing retrieved at all
    if not chunks:
        return {**base, "answer": REFUSAL, "refused": True, "refusal_reason": "no_chunks",
                "total_seconds": round(time.time() - start, 3)}

    # 4.3 — Retrieval too weak: refuse WITHOUT calling the LLM
    if chunks[0]["distance"] > DISTANCE_THRESHOLD:
        return {**base, "answer": REFUSAL, "refused": True, "refusal_reason": "distance_gate",
                "total_seconds": round(time.time() - start, 3)}

    # 2. Build the grounded prompt
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(question, chunks)},
    ]

    # 3. Generate — with provider failover (4.2)
    llm_start = time.time()
    used_model = MODEL
    try:
        response = completion(model=MODEL, messages=messages, max_tokens=MAX_TOKENS)
    except Exception as primary_error:
        print(f"  ⚠️  {MODEL} failed ({type(primary_error).__name__}) — falling back to {FALLBACK_MODEL}")
        try:
            response = completion(model=FALLBACK_MODEL, messages=messages, max_tokens=MAX_TOKENS)
            used_model = FALLBACK_MODEL
        except Exception as fallback_error:
            return {**base, "answer": "Both providers are currently unavailable. Please try again.",
                    "refused": True, "refusal_reason": "all_providers_failed",
                    "error": f"{type(primary_error).__name__} / {type(fallback_error).__name__}",
                    "total_seconds": round(time.time() - start, 3)}

    llm_time = time.time() - llm_start
    text = response.choices[0].message.content.strip()
    refused = is_refusal(text)

    # Flag the contradiction: refusal string present, but an answer followed (INC-006)
    hedged = text.startswith(REFUSAL[:40]) and not refused

    return {
        **base,
        "answer": text,
        "refused": refused,
        "refusal_reason": "model_refused" if refused else None,
        "hedged": hedged,
        "model": used_model,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
        "llm_seconds": round(llm_time, 3),
        "total_seconds": round(time.time() - start, 3),
    }


def main():
    if len(sys.argv) < 2:
        print('Usage: python api/rag.py "your question"')
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
        print(f"  [{s['n']}] {s['title']}  ({s['distance']:.3f})")
        print(f"      {link}")

    print(f"\nbest distance : {result['best_distance']:.4f}")
    print(f"tokens        : {result['input_tokens']} in / {result['output_tokens']} out")
    print(f"timing        : retrieval {result['retrieval_seconds']}s | "
          f"llm {result['llm_seconds']}s | total {result['total_seconds']}s")
    print(f"refused       : {result['refused']}  ({result.get('refusal_reason') or 'n/a'})")
    if result.get("hedged"):
        print("⚠️  HEDGED     : refusal string present but an answer followed (INC-006)")
    print(f"model         : {result.get('model') or 'none (gated)'}")


if __name__ == "__main__":
    main()