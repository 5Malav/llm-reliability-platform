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

load_dotenv()

MODEL = "anthropic/claude-haiku-4-5-20251001"   # DEC-002: Haiku default
TOP_K = 5
MAX_TOKENS = 800


def answer(question, top_k=TOP_K):
    """Answer a question from retrieved documentation. Returns a result dict."""
    start = time.time()

    # 1. Retrieve
    chunks = search(question, top_k=top_k)
    retrieval_time = time.time() - start

    # 2. Build the grounded prompt
    user_message = build_user_message(question, chunks)

    # 3. Generate
    llm_start = time.time()
    response = completion(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=MAX_TOKENS,
    )
    llm_time = time.time() - llm_start

    text = response.choices[0].message.content.strip()
    usage = response.usage

    return {
        "question": question,
        "answer": text,
        "sources": [
            {"n": i, "title": c["title"], "url": c["url"], "distance": c["distance"]}
            for i, c in enumerate(chunks, 1)
        ],
        "best_distance": chunks[0]["distance"] if chunks else None,
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
        "retrieval_seconds": round(retrieval_time, 3),
        "llm_seconds": round(llm_time, 3),
        "total_seconds": round(time.time() - start, 3),
    }


def main():
    if len(sys.argv) < 2:
        print('Usage: python api/rag.py "your question"')
        return

    result = answer(sys.argv[1])

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


if __name__ == "__main__":
    main()