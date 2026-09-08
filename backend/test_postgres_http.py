"""HTTP-level smoke coverage for REelo core endpoints on PostgreSQL."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    url = os.getenv("REELO_DATABASE_URL", "").strip()
    if not url.lower().startswith(("postgres://", "postgresql://")):
        pytest.skip("REELO_DATABASE_URL is not configured for PostgreSQL")

    from main import app

    with TestClient(app) as test_client:
        yield test_client


def test_core_http_flow(client):
    suffix = os.urandom(4).hex()
    username_a = f"httpa_{suffix}"
    username_b = f"httpb_{suffix}"

    a = client.post(
        "/api/auth/register",
        json={"username": username_a, "password": "password123", "display_name": "HTTP A"},
    )
    assert a.status_code == 200, a.text
    token_a = a.json()["token"]
    user_a = a.json()["user"]["id"]

    b = client.post(
        "/api/auth/register",
        json={"username": username_b, "password": "password123", "display_name": "HTTP B"},
    )
    assert b.status_code == 200, b.text
    token_b = b.json()["token"]

    me = client.get("/api/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me.status_code == 200
    assert me.json()["user"]["username"] == username_a

    # Upload is asynchronous: the API stores the file and queues media processing.
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("http-test.mp4", b"REelo PostgreSQL HTTP upload test", "video/mp4")},
        data={"caption": "HTTP PostgreSQL upload test"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert upload.status_code == 200, upload.text
    uploaded = upload.json()
    video_id = uploaded["id"]
    filename = uploaded["filename"]
    assert uploaded["status"] == "processing"
    assert uploaded["mime_type"] == "video/mp4"
    assert uploaded["size"] > 0
    assert uploaded["url"] == f"/media/{filename}"

    media_path = Path(__file__).parent / "media" / filename
    assert media_path.is_file()

    media = client.get(uploaded["url"])
    assert media.status_code == 200
    assert media.content == b"REelo PostgreSQL HTTP upload test"

    # The worker is asynchronous; make the stored record ready here so the
    # remainder of this smoke test can exercise feed/social HTTP endpoints.
    from main import db
    with db() as c:
        c.execute("UPDATE videos SET status='ready' WHERE id=?", (video_id,))

    feed = client.get("/api/feed", headers={"Authorization": f"Bearer {token_b}"})
    assert feed.status_code == 200
    assert any(item["id"] == video_id for item in feed.json()["items"])

    follow = client.post(
        f"/api/users/{user_a}/follow",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert follow.status_code == 200
    assert follow.json()["action"] == "follow"

    like = client.post(
        f"/api/videos/{video_id}/like",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert like.status_code == 200
    assert like.json()["liked"] is True

    comment = client.post(
        f"/api/videos/{video_id}/comments",
        json={"body": "Great"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert comment.status_code == 200, comment.text

    notifications = client.get(
        "/api/notifications",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert notifications.status_code == 200
    assert notifications.json()["unread"] >= 1

    media_path.unlink(missing_ok=True)
