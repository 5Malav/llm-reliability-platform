"""
Embed all chunks using text-embedding-3-small (1536 dims).

Sends chunks to the API in batches, saves progress as it goes, and
retries on transient failures. Safe to re-run — already-embedded
chunks are skipped.

Run:  python ingestion/embed_chunks.py
"""

import json
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

# --- Files ---
CHUNKS_FILE = Path("ingestion/data/chunks.json")
OUT_FILE = Path("ingestion/data/embeddings.json")

# --- Settings (DEC-008) ---
MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
BATCH_SIZE = 100          # chunks per API call
MAX_RETRIES = 3
COST_PER_1M_TOKENS = 0.02  # USD, text-embedding-3-small


def embed_batch(texts):
    """Embed a list of texts. Retries on failure. Returns (vectors, tokens_used)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.embeddings.create(model=MODEL, input=texts)
            vectors = [item.embedding for item in response.data]
            return vectors, response.usage.total_tokens

        except Exception as e:
            if attempt == MAX_RETRIES:
                raise  # out of retries — let it fail loudly
            wait = 2 ** attempt  # 2s, 4s, 8s
            print(f"    ⚠️  attempt {attempt} failed ({type(e).__name__}), retrying in {wait}s...")
            time.sleep(wait)


def load_existing():
    """Load already-embedded chunks so a re-run doesn't re-pay for them."""
    if OUT_FILE.exists():
        done = json.loads(OUT_FILE.read_text())
        print(f"Found {len(done)} already-embedded chunks — resuming.")
        return {d["chunk_id"]: d for d in done}
    return {}


def main():
    chunks = json.loads(CHUNKS_FILE.read_text())
    existing = load_existing()

    # Only embed what we haven't done yet
    todo = [c for c in chunks if c["chunk_id"] not in existing]

    print(f"Total chunks:     {len(chunks)}")
    print(f"Already embedded: {len(existing)}")
    print(f"To embed:         {len(todo)}")

    if not todo:
        print("\nNothing to do — all chunks already embedded.")
        return

    results = dict(existing)
    total_tokens = 0
    start = time.time()

    # Process in batches
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]

        vectors, tokens = embed_batch(texts)
        total_tokens += tokens

        # Pair each chunk with its vector
        for chunk, vector in zip(batch, vectors):
            if len(vector) != DIMENSIONS:
                raise ValueError(
                    f"{chunk['chunk_id']}: expected {DIMENSIONS} dims, got {len(vector)}"
                )
            results[chunk["chunk_id"]] = {
                "chunk_id": chunk["chunk_id"],
                "embedding": vector,
            }

        # Save after every batch — crash-safe
        OUT_FILE.write_text(json.dumps(list(results.values())))

        done = min(i + BATCH_SIZE, len(todo))
        print(f"  embedded {done}/{len(todo)}  ({total_tokens:,} tokens)")

    elapsed = time.time() - start
    cost = (total_tokens / 1_000_000) * COST_PER_1M_TOKENS

    print("\n--- Embedding complete ---")
    print(f"Chunks embedded:  {len(todo)}")
    print(f"Total in file:    {len(results)}")
    print(f"Tokens used:      {total_tokens:,}")
    print(f"Estimated cost:   ${cost:.4f}")
    print(f"Time taken:       {elapsed:.1f}s")
    print(f"Saved to:         {OUT_FILE}")


if __name__ == "__main__":
    main()