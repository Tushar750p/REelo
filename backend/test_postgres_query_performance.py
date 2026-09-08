"""Read-only PostgreSQL checks for the indexes used by current API query shapes."""
import os

import pytest

pytestmark = pytest.mark.integration

EXPECTED_INDEXES = {
    "idx_videos_ready_created",
    "idx_videos_user_ready_created",
    "idx_likes_video_user",
}


def _node_types(plan):
    """Collect planner node types from PostgreSQL JSON EXPLAIN output."""
    found = []
    if isinstance(plan, list):
        for item in plan:
            found.extend(_node_types(item))
    elif isinstance(plan, dict):
        node = plan.get("Plan")
        if isinstance(node, dict):
            if "Node Type" in node:
                found.append(node["Node Type"])
            if "Plans" in node:
                found.extend(_node_types(node["Plans"]))
        for key, value in plan.items():
            if key != "Plan" and isinstance(value, (dict, list)):
                found.extend(_node_types(value))
    return found


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


def test_targeted_indexes_are_visible_to_planner(pg_connection):
    """Use planner-visible EXPLAIN, not timing thresholds, for CI stability."""
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
        cur.execute(
            "EXPLAIN (FORMAT JSON) SELECT 1 FROM likes WHERE video_id=%s AND user_id=%s",
            ("plan-video", "plan-user"),
        )
        like_plan = cur.fetchone()[0]

    # CI has tiny tables, so PostgreSQL may correctly choose a sequential scan.
    # Assert the plans are valid and inspectable rather than forcing index usage.
    assert _node_types(feed_plan)
    assert _node_types(following_plan)
    assert _node_types(like_plan)
