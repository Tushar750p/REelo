"""API-shaped PostgreSQL contract checks.

These checks exercise the same SQL contracts used by the core API without
starting the full HTTP server. They run only when PostgreSQL is configured.
"""
import os

import pytest


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def conn():
    url = os.getenv("REELO_DATABASE_URL", "").strip()
    if not url.lower().startswith(("postgres://", "postgresql://")):
        pytest.skip("REELO_DATABASE_URL is not configured for PostgreSQL")
    import psycopg
    with psycopg.connect(url) as connection:
        yield connection


def test_user_video_feed_like_follow_comment_notification_contract(conn):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notifications WHERE id LIKE 'api-pg-test-%'")
            cur.execute("DELETE FROM comments WHERE id LIKE 'api-pg-test-%'")
            cur.execute("DELETE FROM likes WHERE user_id LIKE 'api-pg-test-%'")
            cur.execute("DELETE FROM follows WHERE follower_id LIKE 'api-pg-test-%'")
            cur.execute("DELETE FROM videos WHERE id LIKE 'api-pg-test-%'")
            cur.execute("DELETE FROM users WHERE id LIKE 'api-pg-test-%'")

            cur.execute(
                "INSERT INTO users (id, username, password_hash, display_name) VALUES (%s,%s,%s,%s),(%s,%s,%s,%s)",
                (
                    "api-pg-test-a", "api_pg_a", "test", "API A",
                    "api-pg-test-b", "api_pg_b", "test", "API B",
                ),
            )
            cur.execute(
                "INSERT INTO videos (id,user_id,filename,caption,status) VALUES (%s,%s,%s,%s,%s)",
                ("api-pg-test-video", "api-pg-test-a", "test.mp4", "hello postgres", "ready"),
            )
            cur.execute(
                "INSERT INTO follows (follower_id,following_id) VALUES (%s,%s)",
                ("api-pg-test-b", "api-pg-test-a"),
            )
            cur.execute(
                "INSERT INTO likes (user_id,video_id) VALUES (%s,%s)",
                ("api-pg-test-b", "api-pg-test-video"),
            )
            cur.execute(
                "UPDATE videos SET likes = likes + 1 WHERE id = %s",
                ("api-pg-test-video",),
            )
            cur.execute(
                "INSERT INTO comments (id,user_id,video_id,body) VALUES (%s,%s,%s,%s)",
                ("api-pg-test-comment", "api-pg-test-b", "api-pg-test-video", "nice"),
            )
            cur.execute(
                "UPDATE videos SET comments = comments + 1 WHERE id = %s",
                ("api-pg-test-video",),
            )
            cur.execute(
                "INSERT INTO notifications (id,recipient_id,actor_id,type,video_id) VALUES (%s,%s,%s,%s,%s)",
                ("api-pg-test-notification", "api-pg-test-a", "api-pg-test-b", "comment", "api-pg-test-video"),
            )

            cur.execute(
                """
                SELECT v.id, v.caption, u.username,
                       CASE WHEN EXISTS (
                           SELECT 1 FROM likes l
                           WHERE l.video_id=v.id AND l.user_id=%s
                       ) THEN 1 ELSE 0 END AS liked
                FROM videos v JOIN users u ON u.id=v.user_id
                WHERE v.status='ready' AND v.id=%s
                """,
                ("api-pg-test-b", "api-pg-test-video"),
            )
            feed = cur.fetchone()
            assert feed == ("api-pg-test-video", "hello postgres", "api_pg_a", 1)

            cur.execute(
                "SELECT likes, comments FROM videos WHERE id=%s",
                ("api-pg-test-video",),
            )
            assert cur.fetchone() == (1, 1)

            cur.execute(
                "SELECT COUNT(*) FROM follows WHERE follower_id=%s AND following_id=%s",
                ("api-pg-test-b", "api-pg-test-a"),
            )
            assert cur.fetchone()[0] == 1

            cur.execute(
                "SELECT COUNT(*) FROM notifications WHERE recipient_id=%s AND read=0",
                ("api-pg-test-a",),
            )
            assert cur.fetchone()[0] == 1
