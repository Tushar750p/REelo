from fastapi import APIRouter, Header, HTTPException
from database_gateway import db

router=APIRouter(prefix="/api/videos",tags=["likes"])

def _uid(authorization):
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        from main import current_user
        return current_user(authorization)
    except Exception:
        return None

@router.get("/{video_id}/like/state")
def like_state(video_id:str,authorization:str|None=Header(default=None)):
    uid=_uid(authorization)
    if not uid: raise HTTPException(401,"Login required")
    with db() as c:
        row=c.execute("SELECT likes FROM videos WHERE id=?",(video_id,)).fetchone()
        if not row: raise HTTPException(404,"Video not found")
        liked=bool(c.execute("SELECT 1 FROM likes WHERE user_id=? AND video_id=?",(uid,video_id)).fetchone())
    return {"liked":liked,"likes":int(row["likes"])}
