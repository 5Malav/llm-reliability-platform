"""
Verify Python can connect to the Postgres+pgvector database.

Run:  python ingestion/db_test.py
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def main():
    print("Connecting to database...")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # 1. Is pgvector installed?
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
    version = cur.fetchone()
    print(f"✅ pgvector version:  {version[0] if version else 'NOT FOUND'}")

    # 2. Does the chunks table exist, and how many rows?
    cur.execute("SELECT COUNT(*) FROM chunks;")
    count = cur.fetchone()[0]
    print(f"✅ chunks table rows: {count}")

    # 3. Can Postgres actually do vector math?
    cur.execute("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector;")
    distance = cur.fetchone()[0]
    print(f"✅ vector distance test: {distance}  (expected 1.0)")

    cur.close()
    conn.close()
    print("\nConnection OK.")


if __name__ == "__main__":
    main()