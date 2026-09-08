"""Optional FFmpeg-backed video processing for REelo.

The pipeline is local-storage based and production-safe by default: it only
processes files that already belong to the authenticated creator. FFmpeg is
optional so the API can run in environments where transcoding is delegated to
an external worker later.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from main import MEDIA, db


VIDEO_PROFILES = {
    "360p": {"height": 360, "video_bitrate": "700k"},
    "540p": {"height": 540, "video_bitrate": "1200k"},
    "720p": {"height": 720, "video_bitrate": "2500k"},
}


def ensure_tables(c):
    c.execute("""CREATE TABLE IF NOT EXISTS video_processing(
        video_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending',
        duration_seconds REAL DEFAULT 0, width INTEGER DEFAULT 0,
        height INTEGER DEFAULT 0, thumbnail TEXT DEFAULT '',
        error TEXT DEFAULT '', updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS video_variants(
        id TEXT PRIMARY KEY, video_id TEXT NOT NULL, profile TEXT NOT NULL,
        filename TEXT NOT NULL, mime_type TEXT NOT NULL DEFAULT 'video/mp4',
        width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(video_id, profile)
    )""")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=300, check=False)


def process_video(video_id: str, source: Path) -> dict:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        with db() as c:
            ensure_tables(c)
            c.execute("INSERT INTO video_processing(video_id,status,error,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(video_id) DO UPDATE SET status=excluded.status,error=excluded.error,updated_at=CURRENT_TIMESTAMP", (video_id, "pending", "FFmpeg is not installed; upload remains available and processing can be delegated to a worker."))
        return {"status": "pending", "reason": "ffmpeg_unavailable", "variants": []}

    probe = _run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-show_entries", "stream=width,height", "-of", "default=noprint_wrappers=1", str(source)])
    if probe.returncode != 0:
        raise RuntimeError(probe.stderr.strip() or "Unable to inspect video")
    duration = 0.0; width = height = 0
    for line in probe.stdout.splitlines():
        if line.startswith("duration="):
            try: duration = max(0.0, float(line.split("=",1)[1]))
            except ValueError: pass
        elif line.startswith("width="):
            try: width = int(line.split("=",1)[1])
            except ValueError: pass
        elif line.startswith("height="):
            try: height = int(line.split("=",1)[1])
            except ValueError: pass

    base = source.stem
    thumb_name = f"{base}-thumb.jpg"
    thumb = MEDIA / thumb_name
    thumb_cmd = [ffmpeg, "-y", "-ss", "00:00:00.500", "-i", str(source), "-frames:v", "1", "-vf", "scale=720:-2", str(thumb)]
    thumb_run = _run(thumb_cmd)
    if thumb_run.returncode != 0:
        raise RuntimeError(thumb_run.stderr.strip() or "Thumbnail generation failed")

    variants = []
    for profile, spec in VIDEO_PROFILES.items():
        if height and height <= spec["height"]:
            target_height = height
        else:
            target_height = spec["height"]
        filename = f"{base}-{profile}.mp4"
        target = MEDIA / filename
        cmd = [ffmpeg, "-y", "-i", str(source), "-vf", f"scale=-2:{target_height}", "-c:v", "libx264", "-preset", "veryfast", "-b:v", spec["video_bitrate"], "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(target)]
        run = _run(cmd)
        if run.returncode != 0:
            raise RuntimeError(run.stderr.strip() or f"Transcoding failed for {profile}")
        variants.append({"profile": profile, "filename": filename, "height": target_height, "url": f"/media/{filename}"})

    with db() as c:
        ensure_tables(c)
        c.execute("INSERT INTO video_processing(video_id,status,duration_seconds,width,height,thumbnail,error,updated_at) VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(video_id) DO UPDATE SET status=excluded.status,duration_seconds=excluded.duration_seconds,width=excluded.width,height=excluded.height,thumbnail=excluded.thumbnail,error='',updated_at=CURRENT_TIMESTAMP", (video_id, "ready", duration, width, height, thumb_name, ""))
        c.execute("DELETE FROM video_variants WHERE video_id=?", (video_id,))
        for item in variants:
            c.execute("INSERT INTO video_variants(id,video_id,profile,filename,width,height) VALUES(?,?,?,?,?,?)", (uuid4().hex, video_id, item["profile"], item["filename"], width if width else 0, item["height"]))
    return {"status": "ready", "duration_seconds": duration, "width": width, "height": height, "thumbnail": f"/media/{thumb_name}", "variants": variants}
