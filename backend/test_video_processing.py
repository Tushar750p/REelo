"""Real FFmpeg smoke coverage for the REelo media pipeline."""
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


def test_ffmpeg_pipeline_generates_thumbnail_variants_and_hls():
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.fail("FFmpeg and ffprobe must be installed for media pipeline tests")

    os.environ.setdefault("REELO_DATABASE_URL", "postgresql://reelo:reelo_test_password@localhost:5432/reelo_test")
    from main import MEDIA, db, hash_password, init_db
    from video_processing import process_video, ensure_tables, VIDEO_PROFILES

    init_db()
    video_id = uuid4().hex
    user_id = uuid4().hex
    source = MEDIA / f"ci-{video_id}.mp4"

    try:
        with db() as c:
            c.execute(
                "INSERT INTO users(id,username,password_hash,display_name) VALUES(?,?,?,?)",
                (user_id, f"ci_{user_id[:12]}", hash_password("ci-password"), "CI Media User"),
            )

        result = subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=240x320:rate=12", "-t", "2", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(source)],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, result.stderr

        with db() as c:
            ensure_tables(c)
            c.execute(
                "INSERT INTO videos(id,user_id,filename,caption,file_size,mime_type,status) VALUES(?,?,?,?,?,?,?)",
                (video_id, user_id, source.name, "CI media test", source.stat().st_size, "video/mp4", "processing"),
            )

        processed = process_video(video_id, source)
        assert processed["status"] == "ready"
        assert processed["duration_seconds"] > 0
        assert processed["width"] == 240
        assert processed["height"] == 320
        assert (MEDIA / Path(processed["thumbnail"]).name).is_file()
        assert processed["hls_url"].endswith("master.m3u8")

        for profile in VIDEO_PROFILES:
            variant = next(item for item in processed["variants"] if item["profile"] == profile)
            assert (MEDIA / variant["filename"]).is_file()

        master = MEDIA / Path(processed["hls_url"]).relative_to("/media")
        assert master.is_file()
        master_text = master.read_text(encoding="utf-8")
        assert "#EXTM3U" in master_text
        assert "360p.m3u8" in master_text
        assert "540p.m3u8" in master_text
        assert "720p.m3u8" in master_text
        assert "RESOLUTION=240x320" in master_text

        with db() as c:
            row = c.execute("SELECT status,duration_seconds,width,height,thumbnail FROM video_processing WHERE video_id=?", (video_id,)).fetchone()
            video = c.execute("SELECT status FROM videos WHERE id=?", (video_id,)).fetchone()
        assert row["status"] == "ready"
        assert row["width"] == 240 and row["height"] == 320
        assert video["status"] == "ready"
    finally:
        source.unlink(missing_ok=True)
        for pattern in (f"ci-{video_id}-thumb.jpg", f"ci-{video_id}-360p.mp4", f"ci-{video_id}-540p.mp4", f"ci-{video_id}-720p.mp4"):
            (MEDIA / pattern).unlink(missing_ok=True)
        hls_dir = MEDIA / "hls" / video_id
        if hls_dir.exists():
            shutil.rmtree(hls_dir)
        with db() as c:
            c.execute("DELETE FROM video_hls WHERE video_id=?", (video_id,))
            c.execute("DELETE FROM video_variants WHERE video_id=?", (video_id,))
            c.execute("DELETE FROM video_processing WHERE video_id=?", (video_id,))
            c.execute("DELETE FROM videos WHERE id=?", (video_id,))
            c.execute("DELETE FROM users WHERE id=?", (user_id,))
