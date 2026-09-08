"""PostgreSQL integration checks for the core persistence schema.

The test is skipped unless REELO_DATABASE_URL points at PostgreSQL, allowing
it to remain safe for the existing SQLite developer workflow.
"""
import os

import pytest


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_connection():
    url = os.getenv("REELO_DATABASE_URL", "").strip()
    if not url.lower().startswith(("postgres://", "postgresql://")):
        pytest.skip("REELO_DATABASE_URL is not configured for PostgreSQL")

    import psycopg

    with psycopg.connect(url) as conn:
        yield conn


def test_core_tables_exist(pg_connection):
    expected = {
        "users",
        "videos",
        "likes",
        "follows",
        "comments",
        "events",
        "notifications",
    }
    with pg_connection.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = ANY(%s)
            """,
            (list(expected),),
        )
        actual = {row[0] for row in cur.fetchall()}
    assert actual == expected


def test_core_constraints_and_round_trip(pg_connection):
    with pg_connection.transaction():
        with pg_connection.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, username, email) VALUES (%s, %s, %s)",
                ("pg-test-user", "pg_test_user", "pg-test@example.invalid"),
            )
            cur.execute(
                "INSERT INTO videos (id, user_id, caption) VALUES (%s, %s, %s)",
                ("pg-test-video", "pg-test-user", "PostgreSQL integration test"),
            )
            cur.execute(
                "INSERT INTO likes (user_id, video_id) VALUES (%s, %s)",
                ("pg-test-user", "pg-test-video"),
            )
            cur.execute(
                "INSERT INTO comments (id, user_id, video_id, text) VALUES (%s, %s, %s, %s)",
                ("pg-test-comment", "pg-test-user", "pg-test-video", "Works"),
            )
            cur.execute(
                "INSERT INTO follows (follower_id, following_id) VALUES (%s, %s)",
                ("pg-test-user", "pg-test-user-2"),
            )
