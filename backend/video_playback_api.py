from fastapi import APIRouter, Header, HTTPException

from main import db, current_user
from video_processing import ensure_tables

router = APIRouter(prefix="/api", tags=["video playback"])


@router.get("/videos/playback")
def playback(filename: str):
    """Return processed playback sources for a stored video filename."""
    filename = filename.strip()
    if not filename or len(filename) > 512:
        raise HTTPException(400, "Invalid filename")
    with db() as c:
        ensure_tables(c)
        video = c.execute(
            "SELECT id,status,filename FROM videos WHERE filename=? LIMIT 1",
            (filename,),
        ).fetchone()
        if not video:
            raise HTTPException(404, "Video not found")
        result = {
            "video_id": video["id"],
            "status": video["status"],
            "source_url": f"/media/{video['filename']}",
            "hls_url": None,
            "thumbnail": None,
            "variants": [],
        }
        processing = c.execute(
            "SELECT status,duration_seconds,width,height,thumbnail FROM video_processing WHERE video_id=?",
            (video["id"],),
        ).fetchone()
        if processing:
            result.update({
                "processing_status": processing["status"],
                "duration_seconds": processing["duration_seconds"],
                "width": processing["width"],
                "height": processing["height"],
                "thumbnail": f"/media/{processing['thumbnail']}" if processing["thumbnail"] else None,
            })
        hls = c.execute(
            "SELECT master_path FROM video_hls WHERE video_id=? LIMIT 1",
            (video["id"],),
        ).fetchone()
        if hls and hls["master_path"]:
            result["hls_url"] = f"/media/{hls['master_path']}"
        variants = c.execute(
            "SELECT profile,filename,width,height FROM video_variants WHERE video_id=? ORDER BY height ASC",
            (video["id"],),
        ).fetchall()
        result["variants"] = [
            {
                "profile": row["profile"],
                "url": f"/media/{row['filename']}",
                "width": row["width"],
                "height": row["height"],
            }
            for row in variants
        ]
    return result


@router.get("/videos/{video_id}/like/state")
def like_state(video_id: str, authorization: str | None = Header(default=None)):
    """Return the authenticated user's current like state and canonical count."""
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    with db() as c:
        video = c.execute("SELECT likes FROM videos WHERE id=?", (video_id,)).fetchone()
        if not video:
            raise HTTPException(404, "Video not found")
        liked = bool(c.execute(
            "SELECT 1 FROM likes WHERE user_id=? AND video_id=?",
            (uid, video_id),
        ).fetchone())
    return {"liked": liked, "likes": int(video["likes"] or 0)}
