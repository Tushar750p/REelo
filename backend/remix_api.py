from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4

from main import current_user, db

router = APIRouter(prefix="/api/remix", tags=["remix"])


def require_user(a):
    uid=current_user(a)
    if not uid: raise HTTPException(401,"Login required")
    return uid


def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS remixes(id TEXT PRIMARY KEY,video_id TEXT NOT NULL,creator_id TEXT NOT NULL,kind TEXT NOT NULL,media_url TEXT NOT NULL,caption TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_remixes_video ON remixes(video_id,created_at)")

class RemixIn(BaseModel):
    media_url:str
    caption:str=""
    kind:str="duet"

@router.post("/{video_id}")
def create_remix(video_id:str,data:RemixIn,authorization:str|None=Header(default=None)):
    uid=require_user(authorization); media=data.media_url.strip(); caption=data.caption.strip(); kind=data.kind.strip().lower()
    if kind not in {"duet","remix","reply"}: raise HTTPException(400,"Invalid remix type")
    if not media or len(media)>1000 or len(caption)>2200: raise HTTPException(400,"Invalid remix data")
    with db() as c:
        ensure_tables(c)
        source=c.execute("SELECT id,user_id FROM videos WHERE id=? AND status='ready'",(video_id,)).fetchone()
        if not source: raise HTTPException(404,"Video not found")
        rid=uuid4().hex
        c.execute("INSERT INTO remixes(id,video_id,creator_id,kind,media_url,caption) VALUES(?,?,?,?,?,?)",(rid,video_id,uid,kind,media,caption))
    return {"id":rid,"source_video_id":video_id,"kind":kind,"media_url":media,"caption":caption}

@router.get("/{video_id}")
def list_remixes(video_id:str,limit:int=30):
    limit=max(1,min(limit,100))
    with db() as c:
        ensure_tables(c)
        rows=c.execute("SELECT r.*,u.username,u.display_name FROM remixes r JOIN users u ON u.id=r.creator_id WHERE r.video_id=? ORDER BY r.created_at DESC LIMIT ?",(video_id,limit)).fetchall()
    return {"items":[dict(r) for r in rows]}
