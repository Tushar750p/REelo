"""HTTP-level smoke coverage for REelo core endpoints on PostgreSQL."""
import os
import subprocess
import tempfile
import time
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

    # Use a valid tiny MP4 so the real asynchronous worker can process it.
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "http-test.mp4"
        generated = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x568:r=24",
                "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert generated.returncode == 0, generated.stderr
        upload_bytes = source.read_bytes()

        upload = client.post(
            "/api/videos/upload",
            files={"file": ("http-test.mp4", upload_bytes, "video/mp4")},
            data={"caption": "HTTP PostgreSQL upload test"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert upload.status_code == 200, upload.text
        uploaded = upload.json()
        video_id = uploaded["id"]
        filename = uploaded["filename"]
        assert uploaded["status"] == "processing"
        assert uploaded["mime_type"] == "video/mp4"
        assert uploaded["size"] == len(upload_bytes)
        assert uploaded["url"] == f"/media/{filename}"

        media_path = Path(__file__).parent / "media" / filename
        assert media_path.is_file()

        media = client.get(uploaded["url"])
        assert media.status_code == 200
        assert media.content == upload_bytes

        # Wait for the real worker to finish before exercising feed/social APIs.
        from main import db
        deadline = time.time() + 15
        while time.time() < deadline:
            with db() as c:
                row = c.execute("SELECT status FROM videos WHERE id=?", (video_id,)).fetchone()
            if row and row["status"] == "ready":
                break
            if row and row["status"] == "failed":
                pytest.fail("Video processing failed in PostgreSQL HTTP smoke test")
            time.sleep(0.1)
        else:
            pytest.fail("Timed out waiting for video processing")

        # Follow the creator before reading the following feed. Using the explicit
        # following mode keeps this smoke test focused on the core follow/feed
        # contract rather than depending on recommendation ranking heuristics.
        follow = client.post(
            f"/api/users/{user_a}/follow",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert follow.status_code == 200
        assert follow.json()["action"] == "follow"

        feed = client.get(
            "/api/feed?following=true",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert feed.status_code == 200
        assert any(item["id"] == video_id for item in feed.json()["items"])

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
