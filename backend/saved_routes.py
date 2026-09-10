from fastapi import APIRouter, Header, HTTPException
from database_gateway import db

router = APIRouter()


def _uid(authorization):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Login required")
    # Import the canonical verifier from main without duplicating token logic.
    from main import current_user
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def _ensure_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS saved_videos(user_id TEXT NOT NULL,video_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,video_id))")


@router.post("/api/videos/{video_id}/save")
def save_video(video_id: str, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    with db() as c:
        _ensure_table(c)
        video = c.execute("SELECT id FROM videos WHERE id=? AND status='ready'", (video_id,)).fetchone()
        if not video:
            raise HTTPException(404, "Video not found")
        deleted = c.execute("DELETE FROM saved_videos WHERE user_id=? AND video_id=?", (uid, video_id)).rowcount
        if deleted:
            return {"saved": False}
        c.execute("INSERT INTO saved_videos(user_id,video_id) VALUES(?,?) ON CONFLICT(user_id,video_id) DO NOTHING", (uid, video_id))
    return {"saved": True}


@router.get("/api/saved")
def saved_videos(limit: int = 50, offset: int = 0, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with db() as c:
        _ensure_table(c)
        rows = c.execute("SELECT v.*,u.username,u.display_name,1 AS saved FROM saved_videos s JOIN videos v ON v.id=s.video_id JOIN users u ON u.id=v.user_id WHERE s.user_id=? AND v.status='ready' ORDER BY s.created_at DESC LIMIT ? OFFSET ?", (uid, limit, offset)).fetchall()
        total = c.execute("SELECT COUNT(*) FROM saved_videos s JOIN videos v ON v.id=s.video_id WHERE s.user_id=? AND v.status='ready'", (uid,)).fetchone()[0]
    return {"items": [dict(x) for x in rows], "total": total, "limit": limit, "offset": offset}
