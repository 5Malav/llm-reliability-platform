"""
Cut cleaned docs into overlapping chunks, ready for embedding.

For each cleaned JSON doc:
  1. Count its tokens
  2. Slide a 500-token window across it, stepping forward 425 tokens
     (so consecutive chunks share ~75 tokens = 15% overlap)
  3. Save each chunk with its source info

Run:  python ingestion/chunk_docs.py
"""

import json
from pathlib import Path
import tiktoken

# --- Folders ---
IN_DIR = Path("ingestion/data/processed")
OUT_FILE = Path("ingestion/data/chunks.json")

# --- Chunking settings (DEC-005) ---
CHUNK_SIZE = 500      # tokens per chunk
OVERLAP = 75          # tokens shared between consecutive chunks (15%)
STEP = CHUNK_SIZE - OVERLAP   # how far we move the window each time = 425
MIN_CHUNK_TOKENS = 100        # drop trailing scraps — already covered by overlap

# The tokenizer — turns text into tokens so we can count accurately
encoder = tiktoken.get_encoding("cl100k_base")


def chunk_text(text):
    """Cut one document's text into overlapping chunks. Returns a list of strings."""

    # Turn the text into a list of tokens
    tokens = encoder.encode(text)

    # If the doc is smaller than one chunk, it IS one chunk
    if len(tokens) <= CHUNK_SIZE:
        return [text]

    chunks = []
    start = 0

    # Slide the window across the token list
    while start < len(tokens):
        end = start + CHUNK_SIZE
        window = tokens[start:end]

        # Skip trailing scraps — too small to hold a complete idea, and the
        # content already lives (complete) in the previous chunk via overlap
        if len(window) >= MIN_CHUNK_TOKENS:
            chunks.append(encoder.decode(window))

        # Move forward by STEP (not CHUNK_SIZE) — that's what creates the overlap
        start += STEP

    return chunks

DOCS_BASE_URL = "https://supabase.com/docs/"


def build_url(source_path):
    """Turn a source file path into a live Supabase docs URL.

    Returns None for _partials — those are fragments injected into other
    pages and have no standalone URL. An absent link is honest; a wrong
    link is worse than none.
    """
    if source_path.startswith("_partials"):
        return None

    # guides/auth/x.mdx  ->  https://supabase.com/docs/guides/auth/x
    return DOCS_BASE_URL + source_path.removesuffix(".mdx")

def get_doc_type(source_path):
    """Derive the document type from its top-level folder."""
    top = source_path.split("/")[0]

    if top == "guides":
        return "guide"
    if top == "troubleshooting":
        return "troubleshooting"
    if top == "_partials":
        return "partial"
    return "other"

def process_doc(doc):
    """Turn one document into a list of chunk records."""
    pieces = chunk_text(doc["content"])
    records = []

    # Unique doc key from the full path — filenames alone collide across
    # folders (guides/ai/concepts.mdx vs guides/realtime/concepts.mdx). See INC-005.
    doc_key = doc["source_path"].removesuffix(".mdx").replace("/", "__")

    for i, piece in enumerate(pieces):
        records.append({
            "chunk_id": f"{doc_key}__{i}",
            "doc_id": doc_key,
            "title": doc["title"],
            "source_path": doc["source_path"],
            "url": build_url(doc["source_path"]),
            "doc_type": get_doc_type(doc["source_path"]),
            "chunk_index": i,
            "total_chunks": len(pieces),
            "text": piece,
            "token_count": len(encoder.encode(piece)),
        })

    return records

def main():
    files = sorted(IN_DIR.glob("*.json"))
    all_chunks = []

    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        all_chunks.extend(process_doc(doc))

    # Save everything into one file
    OUT_FILE.write_text(json.dumps(all_chunks, indent=2), encoding="utf-8")

    # Summary
    token_counts = [c["token_count"] for c in all_chunks]
    print("\n--- Chunking complete ---")
    print(f"Documents in:      {len(files)}")
    print(f"Chunks out:        {len(all_chunks)}")
    print(f"Avg chunks/doc:    {len(all_chunks) / len(files):.1f}")
    print(f"Avg tokens/chunk:  {sum(token_counts) // len(token_counts)}")
    print(f"Smallest chunk:    {min(token_counts)} tokens")
    print(f"Largest chunk:     {max(token_counts)} tokens")
    print(f"Saved to:          {OUT_FILE}")


if __name__ == "__main__":
    main()