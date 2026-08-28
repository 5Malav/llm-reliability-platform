"""
Semantic search over the chunk store.

Embeds a question with the same model used for chunks, then finds the
nearest vectors in Postgres.

Run:  python retrieval/search.py "how do I set up GitHub auth?"
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

DATABASE_URL = os.getenv("DATABASE_URL")
MODEL = "text-embedding-3-small"   # MUST match the model used for chunks


def embed_query(question):
    """Turn a question into a vector using the same model as the chunks."""
    response = client.embeddings.create(model=MODEL, input=question)
    return response.data[0].embedding


def search(question, top_k=5, doc_type=None):
    """Return the top_k chunks most similar in meaning to the question."""
    vector = embed_query(question)

    sql = """
        SELECT chunk_id, title, url, doc_type, text,
               embedding <=> %s::vector AS distance
        FROM chunks
    """
    params = [str(vector)]

    if doc_type:
        sql += " WHERE doc_type = %s"
        params.append(doc_type)

    sql += " ORDER BY distance LIMIT %s;"
    params.append(top_k)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "chunk_id": r[0],
            "title": r[1],
            "url": r[2],
            "doc_type": r[3],
            "text": r[4],
            "distance": r[5],
        }
        for r in rows
    ]


def main():
    if len(sys.argv) < 2:
        print('Usage: python retrieval/search.py "your question here"')
        return

    question = sys.argv[1]
    results = search(question)

    print(f"\nQUESTION: {question}\n")
    print("=" * 70)

    for i, r in enumerate(results, 1):
        preview = r["text"].replace("\n", " ")[:120]
        print(f"\n[{i}] distance {r['distance']:.4f}  |  {r['doc_type']}")
        print(f"    {r['title']}")
        print(f"    {r['url']}")
        print(f"    {preview}...")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()