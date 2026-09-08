"""Background-friendly video processing primitives for REelo.

The worker is intentionally dependency-light: FFmpeg is invoked as an external
process when installed. Jobs are persisted in SQLite so a separate worker
process can safely pick them up. Actual production deployment should run this
worker outside the web process and place media on object storage/CDN.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

ROOT = Path(__file__).parent
MEDIA = ROOT / "media"
MEDIA.mkdir(exist_ok=True)
DB = ROOT / "reelo.db"


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_pipeline_tables(c):
    c.execute("""CREATE TABLE IF NOT EXISTS video_processing_jobs(
        id TEXT PRIMARY KEY, video_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'queued',
        attempts INTEGER NOT NULL DEFAULT 0, error TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, started_at TEXT, completed_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS video_variants(
        id TEXT PRIMARY KEY, video_id TEXT NOT NULL, kind TEXT NOT NULL,
        path TEXT NOT NULL, width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
        bitrate INTEGER DEFAULT 0, duration REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(video_id, kind)
    )""")


def enqueue(video_id: str) -> str:
    with db() as c:
        ensure_pipeline_tables(c)
        job_id = uuid4().hex
        c.execute("INSERT OR IGNORE INTO video_processing_jobs(id,video_id,status) VALUES(?,?,?)", (job_id, video_id, "queued"))
        row = c.execute("SELECT id FROM video_processing_jobs WHERE video_id=?", (video_id,)).fetchone()
        c.execute("UPDATE videos SET status='processing' WHERE id=?", (video_id,))
        return str(row[0])


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)


def process_job(job_id: str) -> dict:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        with db() as c:
            c.execute("UPDATE video_processing_jobs SET status='pending', error=? WHERE id=?", ("FFmpeg is not installed", job_id))
        return {"status": "pending", "reason": "ffmpeg_unavailable"}

    with db() as c:
        ensure_pipeline_tables(c)
        job = c.execute("SELECT * FROM video_processing_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise ValueError("Processing job not found")
        video = c.execute("SELECT * FROM videos WHERE id=?", (job["video_id"],)).fetchone()
        if not video:
            raise ValueError("Video not found")
        source = MEDIA / video["filename"]
        if not source.exists():
            raise FileNotFoundError(str(source))
        c.execute("UPDATE video_processing_jobs SET status='processing',attempts=attempts+1,started_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), job_id))

    out_dir = MEDIA / "processed" / str(video["id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        probe = [ffmpeg, "-i", str(source), "-hide_banner"]
        # A lightweight transcode path; deployments can tune codecs/bitrates.
        for kind, scale, bitrate in (("360p", "scale=-2:360", "800k"), ("540p", "scale=-2:540", "1400k"), ("720p", "scale=-2:720", "2500k")):
            target = out_dir / f"{kind}.mp4"
            _run([ffmpeg, "-y", "-i", str(source), "-vf", scale, "-c:v", "libx264", "-preset", "veryfast", "-b:v", bitrate, "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(target)])

        hls_dir = out_dir / "hls"
        hls_dir.mkdir(exist_ok=True)
        playlist = hls_dir / "index.m3u8"
        _run([ffmpeg, "-y", "-i", str(source), "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k", "-c:a", "aac", "-b:a", "128k", "-f", "hls", "-hls_time", "4", "-hls_playlist_type", "vod", "-hls_segment_filename", str(hls_dir / "segment_%05d.ts"), str(playlist)])

        with db() as c:
            ensure_pipeline_tables(c)
            for kind in ("360p", "540p", "720p"):
                p = out_dir / f"{kind}.mp4"
                c.execute("INSERT OR REPLACE INTO video_variants(id,video_id,kind,path) VALUES(?,?,?,?)", (uuid4().hex, video["id"], kind, str(p.relative_to(MEDIA)).replace(os.sep, "/")))
            c.execute("INSERT OR REPLACE INTO video_variants(id,video_id,kind,path) VALUES(?,?,?,?)", (uuid4().hex, video["id"], "hls", str(playlist.relative_to(MEDIA)).replace(os.sep, "/")))
            c.execute("UPDATE videos SET status='ready' WHERE id=?", (video["id"],))
            c.execute("UPDATE video_processing_jobs SET status='completed',completed_at=?,error='' WHERE id=?", (datetime.now(timezone.utc).isoformat(), job_id))
        return {"status": "completed", "video_id": video["id"], "hls": f"/media/{playlist.relative_to(MEDIA).as_posix()}"}
    except Exception as exc:
        with db() as c:
            c.execute("UPDATE videos SET status='failed' WHERE id=?", (video["id"],))
            c.execute("UPDATE video_processing_jobs SET status='failed',error=? WHERE id=?", (str(exc)[:1000], job_id))
        raise


def run_once(limit: int = 1) -> list[dict]:
    results = []
    with db() as c:
        ensure_pipeline_tables(c)
        jobs = c.execute("SELECT id FROM video_processing_jobs WHERE status IN ('queued','retry') ORDER BY created_at LIMIT ?", (max(1, min(limit, 10)),)).fetchall()
    for row in jobs:
        try:
            results.append(process_job(str(row["id"])))
        except Exception as exc:
            results.append({"status": "failed", "error": str(exc)})
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    if args.once:
        print(json.dumps(run_once(args.limit)))
