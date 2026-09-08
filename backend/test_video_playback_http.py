"""HTTP contract coverage for processed adaptive video playback metadata."""
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


def test_playback_metadata_http_returns_hls_and_variants():
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.fail("FFmpeg and ffprobe must be installed for playback integration tests")

    os.environ.setdefault("REELO_DATABASE_URL", "postgresql://reelo:reelo_test_password@localhost:5432/reelo_test")
    from fastapi.testclient import TestClient
    from main import MEDIA, app, db, hash_password, init_db
    from video_processing import VIDEO_PROFILES, ensure_tables, process_video

    init_db()
    video_id = uuid4().hex
    user_id = uuid4().hex
    source = MEDIA / f"http-{video_id}.mp4"
    client = TestClient(app)

    try:
        with db() as c:
            c.execute(
                "INSERT INTO users(id,username,password_hash,display_name) VALUES(?,?,?,?)",
                (user_id, f"ci_{user_id[:12]}", hash_password("ci-password"), "CI Playback User"),
            )

        generated = subprocess.run(
            [
                ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=320x568:rate=12",
                "-t", "2", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(source),
            ],
            capture_output=True, text=True, timeout=120,
        )
        assert generated.returncode == 0, generated.stderr

        with db() as c:
            ensure_tables(c)
            c.execute(
                "INSERT INTO videos(id,user_id,filename,caption,file_size,mime_type,status) VALUES(?,?,?,?,?,?,?)",
                (video_id, user_id, source.name, "HTTP adaptive playback test", source.stat().st_size, "video/mp4", "processing"),
            )

        processed = process_video(video_id, source)
        assert processed["status"] == "ready"

        response = client.get("/api/videos/playback", params={"filename": source.name})
        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["video_id"] == video_id
        assert payload["status"] == "ready"
        assert payload["source_url"] == f"/media/{source.name}"
        assert payload["hls_url"] == processed["hls_url"]
        assert payload["thumbnail"] == f"/media/{Path(processed['thumbnail']).name}"
        assert payload["duration_seconds"] > 0
        assert payload["width"] == 320
        assert payload["height"] == 568

        variants = {item["profile"]: item for item in payload["variants"]}
        assert set(variants) == set(VIDEO_PROFILES)
        for profile in VIDEO_PROFILES:
            assert variants[profile]["url"].startswith("/media/")
            assert (MEDIA / Path(variants[profile]["url"]).name).is_file()

        master_path = MEDIA / Path(processed["hls_url"]).relative_to("/media")
        assert master_path.is_file()
        assert client.get(payload["hls_url"]).status_code == 200
        assert client.get(variants["360p"]["url"]).status_code == 200
        assert client.get(variants["720p"]["url"]).status_code == 200

        missing = client.get("/api/videos/playback", params={"filename": "does-not-exist.mp4"})
        assert missing.status_code == 404
    finally:
        source.unlink(missing_ok=True)
        for pattern in (
            f"http-{video_id}-thumb.jpg",
            f"http-{video_id}-360p.mp4",
            f"http-{video_id}-540p.mp4",
            f"http-{video_id}-720p.mp4",
        ):
            (MEDIA / pattern).unlink(missing_ok=True)
        hls_dir = MEDIA / "hls" / video_id
        if hls_dir.exists():
            shutil.rmtree(hls_dir)
        with db() as c:
            for table in ("video_hls", "video_variants", "video_processing"):
                c.execute(f"DELETE FROM {table} WHERE video_id=?", (video_id,))
            c.execute("DELETE FROM videos WHERE id=?", (video_id,))
            c.execute("DELETE FROM users WHERE id=?", (user_id,))
