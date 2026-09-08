"""Read-only PostgreSQL checks for the indexes used by current API query shapes."""
import os

import pytest

pytestmark = pytest.mark.integration

EXPECTED_INDEXES = {
    "idx_videos_ready_created",
    "idx_videos_user_ready_created",
    "idx_likes_video_user",
}


@pytest.fixture(scope="module")
def pg_connection():
    url = os.getenv("REELO_DATABASE_URL", "").strip()
    if not url.lower().startswith(("postgres://", "postgresql://")):
        pytest.skip("REELO_DATABASE_URL is not configured for PostgreSQL")

    import psycopg

    with psycopg.connect(url) as conn:
        yield conn


def test_performance_indexes_exist(pg_connection):
    with pg_connection.cursor() as cur:
        cur.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname = ANY(%s)
            """,
            (list(EXPECTED_INDEXES),),
        )
        actual = {row[0] for row in cur.fetchall()}
    assert actual == EXPECTED_INDEXES


def test_feed_plans_are_plannable(pg_connection):
    with pg_connection.cursor() as cur:
        cur.execute(
            "EXPLAIN (FORMAT JSON) SELECT id FROM videos WHERE status='ready' ORDER BY created_at DESC LIMIT 20"
        )
        feed_plan = cur.fetchone()[0]
        cur.execute(
            "EXPLAIN (FORMAT JSON) SELECT id FROM videos WHERE user_id=%s AND status='ready' ORDER BY created_at DESC LIMIT 20",
            ("plan-user",),
        )
        following_plan = cur.fetchone()[0]
    assert feed_plan and following_plan
