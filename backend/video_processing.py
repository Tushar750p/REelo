"""FFmpeg-backed video processing, background queue, and HLS streaming for REelo."""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from uuid import uuid4

from main import MEDIA, db

VIDEO_PROFILES = {
    "360p": {"height": 360, "video_bitrate": "700k", "bandwidth": 900000},
    "540p": {"height": 540, "video_bitrate": "1200k", "bandwidth": 1500000},
    "720p": {"height": 720, "video_bitrate": "2500k", "bandwidth": 3000000},
}

_jobs: Queue[str] = Queue(maxsize=100)
_worker_started = False
_worker_lock = threading.Lock()


def ensure_tables(c):
    c.execute("""CREATE TABLE IF NOT EXISTS video_processing(
        video_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending',
        duration_seconds REAL DEFAULT 0, width INTEGER DEFAULT 0,
        height INTEGER DEFAULT 0, thumbnail TEXT DEFAULT '', error TEXT DEFAULT '',
        attempts INTEGER DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS video_variants(
        id TEXT PRIMARY KEY, video_id TEXT NOT NULL, profile TEXT NOT NULL,
        filename TEXT NOT NULL, mime_type TEXT NOT NULL DEFAULT 'video/mp4',
        width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(video_id, profile)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS video_hls(
        video_id TEXT PRIMARY KEY, master_path TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    try:
        c.execute("ALTER TABLE video_processing ADD COLUMN attempts INTEGER DEFAULT 0")
    except Exception:
        pass


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=600, check=False)


def _set_status(video_id: str, status: str, error: str = ""):
    with db() as c:
        ensure_tables(c)
        c.execute("UPDATE video_processing SET status=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE video_id=?", (status, error[:1000], video_id))
        if status == "processing":
            c.execute("UPDATE video_processing SET attempts=COALESCE(attempts,0)+1 WHERE video_id=?", (video_id,))
        if status == "processing":
            c.execute("UPDATE videos SET status='processing' WHERE id=?", (video_id,))
        elif status == "ready":
            c.execute("UPDATE videos SET status='ready' WHERE id=?", (video_id,))
        elif status == "failed":
            c.execute("UPDATE videos SET status='failed' WHERE id=?", (video_id,))


def _make_hls(video_id: str, source: Path, base: str, source_width: int = 0, source_height: int = 0) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is not installed")
    hls_dir = MEDIA / f"hls/{video_id}"
    hls_dir.mkdir(parents=True, exist_ok=True)
    playlists = []
    for profile, spec in VIDEO_PROFILES.items():
        target_height = min(source_height, spec["height"]) if source_height else spec["height"]
        target_width = 0
        if source_width and source_height:
            target_width = max(2, int(round((source_width * target_height / source_height) / 2) * 2))
        playlist = hls_dir / f"{profile}.m3u8"
        cmd = [ffmpeg, "-y", "-i", str(source), "-vf", f"scale=-2:{target_height}", "-c:v", "libx264", "-preset", "veryfast", "-b:v", spec["video_bitrate"], "-c:a", "aac", "-b:a", "128k", "-f", "hls", "-hls_time", "4", "-hls_playlist_type", "vod", "-hls_flags", "independent_segments", "-hls_segment_filename", str(hls_dir / f"{profile}-%05d.ts"), str(playlist)]
        run = _run(cmd)
        if run.returncode != 0:
            raise RuntimeError(run.stderr.strip() or f"HLS generation failed for {profile}")
        playlists.append((profile, playlist, spec["bandwidth"], target_width, target_height))
    master = hls_dir / "master.m3u8"
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for profile, playlist, bandwidth, width, height in playlists:
        resolution = f"{width}x{height}" if width else f"720x{height}"
        lines.extend([f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution}", f"{profile}.m3u8"])
    master.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with db() as c:
        ensure_tables(c)
        c.execute("INSERT INTO video_hls(video_id,master_path) VALUES(?,?) ON CONFLICT(video_id) DO UPDATE SET master_path=excluded.master_path,created_at=CURRENT_TIMESTAMP", (video_id, str(master.relative_to(MEDIA)).replace("\\", "/")))
    return f"/media/{master.relative_to(MEDIA).as_posix()}"


def process_video(video_id: str, source: Path) -> dict:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        with db() as c:
            ensure_tables(c)
            c.execute("INSERT INTO video_processing(video_id,status,error,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(video_id) DO UPDATE SET status=excluded.status,error=excluded.error,updated_at=CURRENT_TIMESTAMP", (video_id, "pending", "FFmpeg is not installed; processing is waiting for a worker environment."))
        return {"status": "pending", "reason": "ffmpeg_unavailable", "variants": []}

    _set_status(video_id, "processing")
    probe = _run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-show_entries", "stream=width,height", "-of", "default=noprint_wrappers=1", str(source)])
    if probe.returncode != 0:
        raise RuntimeError(probe.stderr.strip() or "Unable to inspect video")
    duration = 0.0; width = height = 0
    for line in probe.stdout.splitlines():
        if line.startswith("duration="):
            try: duration = max(0.0, float(line.split("=", 1)[1]))
            except ValueError: pass
        elif line.startswith("width="):
            try: width = int(line.split("=", 1)[1])
            except ValueError: pass
        elif line.startswith("height="):
            try: height = int(line.split("=", 1)[1])
            except ValueError: pass

    base = source.stem
    thumb_name = f"{base}-thumb.jpg"
    thumb = MEDIA / thumb_name
    thumb_run = _run([ffmpeg, "-y", "-ss", "00:00:00.500", "-i", str(source), "-frames:v", "1", "-vf", "scale=720:-2", str(thumb)])
    if thumb_run.returncode != 0:
        raise RuntimeError(thumb_run.stderr.strip() or "Thumbnail generation failed")

    variants = []
    for profile, spec in VIDEO_PROFILES.items():
        target_height = min(height, spec["height"]) if height else spec["height"]
        filename = f"{base}-{profile}.mp4"
        target = MEDIA / filename
        run = _run([ffmpeg, "-y", "-i", str(source), "-vf", f"scale=-2:{target_height}", "-c:v", "libx264", "-preset", "veryfast", "-b:v", spec["video_bitrate"], "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(target)])
        if run.returncode != 0:
            raise RuntimeError(run.stderr.strip() or f"Transcoding failed for {profile}")
        variants.append({"profile": profile, "filename": filename, "height": target_height, "url": f"/media/{filename}"})

    hls_url = _make_hls(video_id, source, base, width, height)
    with db() as c:
        ensure_tables(c)
        c.execute("INSERT INTO video_processing(video_id,status,duration_seconds,width,height,thumbnail,error,updated_at) VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(video_id) DO UPDATE SET status='ready',duration_seconds=excluded.duration_seconds,width=excluded.width,height=excluded.height,thumbnail=excluded.thumbnail,error='',updated_at=CURRENT_TIMESTAMP", (video_id, "ready", duration, width, height, thumb_name, ""))
        c.execute("UPDATE videos SET status='ready' WHERE id=?", (video_id,))
        c.execute("DELETE FROM video_variants WHERE video_id=?", (video_id,))
        for item in variants:
            c.execute("INSERT INTO video_variants(id,video_id,profile,filename,width,height) VALUES(?,?,?,?,?,?)", (uuid4().hex, video_id, item["profile"], item["filename"], width or 0, item["height"]))
    return {"status": "ready", "duration_seconds": duration, "width": width, "height": height, "thumbnail": f"/media/{thumb_name}", "hls_url": hls_url, "variants": variants}


def enqueue_video(video_id: str):
    """Queue a video without blocking the upload request."""
    with db() as c:
        ensure_tables(c)
        c.execute("UPDATE videos SET status='processing' WHERE id=?", (video_id,))
        c.execute("INSERT INTO video_processing(video_id,status,error,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(video_id) DO UPDATE SET status='queued',error='',updated_at=CURRENT_TIMESTAMP", (video_id, "queued", ""))
    try:
        _jobs.put_nowait(video_id)
    except Exception:
        _set_status(video_id, "pending", "Processing queue is temporarily full")
    return video_id


def _worker():
    while True:
        try:
            video_id = _jobs.get(timeout=2)
        except Empty:
            continue
        try:
            with db() as c:
                row = c.execute("SELECT filename FROM videos WHERE id=?", (video_id,)).fetchone()
            if row:
                source = MEDIA / row["filename"]
                if source.exists():
                    process_video(video_id, source)
                else:
                    _set_status(video_id, "failed", "Source video file is missing")
        except Exception as exc:
            _set_status(video_id, "failed", str(exc))
        finally:
            _jobs.task_done()


def start_video_worker():
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        thread = threading.Thread(target=_worker, name="reelo-video-worker", daemon=True)
        thread.start()
        # Resume videos that were uploaded before the worker started.
        with db() as c:
            ensure_tables(c)
            rows = c.execute("SELECT v.id FROM videos v LEFT JOIN video_processing p ON p.video_id=v.id WHERE v.status='ready' AND p.video_id IS NULL AND v.filename NOT LIKE ? LIMIT 20", ("http%",)).fetchall()
        for row in rows:
            enqueue_video(row["id"])
