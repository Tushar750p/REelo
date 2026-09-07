from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4

from main import current_user, db

router = APIRouter(prefix="/api/recommendations", tags=["recommendation-learning"])

ALLOWED = {"impression", "watch", "progress", "complete", "skip", "dismiss", "like", "comment", "share", "save", "rewatch"}

class FeedbackIn(BaseModel):
    video_id: str
    action: str
    seconds: float = 0.0

@router.post("/feedback")
def feedback(data: FeedbackIn, authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    action = data.action.strip().lower()
    if action not in ALLOWED:
        raise HTTPException(400, "Unsupported feedback action")
    seconds = max(0.0, min(float(data.seconds or 0), 3600.0))
    with db() as c:
        if not c.execute("SELECT 1 FROM videos WHERE id=? AND status='ready'", (data.video_id,)).fetchone():
            raise HTTPException(404, "Video not found")
        c.execute(
            "INSERT INTO events(id,user_id,video_id,action,seconds) VALUES(?,?,?,?,?)",
            (uuid4().hex, uid, data.video_id, action, seconds),
        )
    return {"ok": True, "video_id": data.video_id, "action": action, "seconds": seconds}

@router.get("/signals")
def signals(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    with db() as c:
        rows = c.execute(
            """
            SELECT video_id,
                   SUM(CASE WHEN action IN ('watch','progress','complete','rewatch') THEN seconds ELSE 0 END) watch_seconds,
                   SUM(CASE WHEN action IN ('skip','dismiss') THEN 1 ELSE 0 END) negative,
                   SUM(CASE WHEN action IN ('like','comment','share','save') THEN 1 ELSE 0 END) positive
            FROM events WHERE user_id=? AND created_at>=datetime('now','-7 days')
            GROUP BY video_id ORDER BY MAX(created_at) DESC LIMIT 200
            """,
            (uid,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}
