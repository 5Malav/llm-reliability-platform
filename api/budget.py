"""
Daily question limit — protects the LLM bill on a public demo.

One row per day in the database, shared by every copy of the app and
surviving restarts. Counting is a single SQL step, so two requests
arriving at the same moment can never both slip past the limit.
"""

import os

import psycopg2

DEFAULT_LIMIT = 100


def _run(sql):
    """Run one statement, commit, always close the connection."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone() if cur.description else None
    finally:
        conn.close()


def create_table():
    """Create the counter table if it doesn't exist yet (safe to run every startup)."""
    _run("""
        CREATE TABLE IF NOT EXISTS daily_usage (
            day       DATE PRIMARY KEY,
            questions INTEGER NOT NULL
        )
    """)


def over_limit():
    """Count this question. True if today's limit was already used up."""
    limit = int(os.getenv("DAILY_QUESTION_LIMIT", DEFAULT_LIMIT))
    (count,) = _run("""
        INSERT INTO daily_usage (day, questions) VALUES (CURRENT_DATE, 1)
        ON CONFLICT (day) DO UPDATE SET questions = daily_usage.questions + 1
        RETURNING questions
    """)
    return count > limit