from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from main import current_user, db

router = APIRouter(prefix="/api/stories", tags=["stories"])


def require_user(a):
    uid = current_user(a)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS stories(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,media_url TEXT NOT NULL,caption TEXT DEFAULT '',expires_at TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS story_views(story_id TEXT NOT NULL,user_id TEXT NOT NULL,viewed_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(story_id,user_id))")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stories_expiry ON stories(expires_at)")


class StoryIn(BaseModel):
    media_url: str
    caption: str = ""


@router.get("")
def list_stories(authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
    with db() as c:
        ensure_tables(c)
        rows = c.execute("""
            SELECT s.*,u.username,u.display_name,
                   CASE WHEN sv.user_id IS NULL THEN 0 ELSE 1 END viewed,
                   (SELECT COUNT(*) FROM story_views x WHERE x.story_id=s.id) views
            FROM stories s JOIN users u ON u.id=s.user_id
            LEFT JOIN story_views sv ON sv.story_id=s.id AND sv.user_id=?
            WHERE s.expires_at>? ORDER BY s.created_at DESC LIMIT 100
        """,(uid,now)).fetchall()
    return {"items":[dict(r) for r in rows]}


@router.post("")
def create_story(data: StoryIn, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    media = data.media_url.strip()
    caption = data.caption.strip()
    if not media or len(media) > 1000 or len(caption) > 500:
        raise HTTPException(400, "Invalid story")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires = (now + timedelta(hours=24)).isoformat().replace('+00:00','Z')
    sid = uuid4().hex
    with db() as c:
        ensure_tables(c)
        c.execute("INSERT INTO stories(id,user_id,media_url,caption,expires_at) VALUES(?,?,?,?,?)",(sid,uid,media,caption,expires))
    return {"id":sid,"media_url":media,"caption":caption,"expires_at":expires}


@router.post("/{story_id}/view")
def view_story(story_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
    with db() as c:
        ensure_tables(c)
        row=c.execute("SELECT user_id FROM stories WHERE id=? AND expires_at>?",(story_id,now)).fetchone()
        if not row: raise HTTPException(404,"Story not found")
        c.execute("INSERT OR IGNORE INTO story_views(story_id,user_id) VALUES(?,?)",(story_id,uid))
    return {"ok":True}


@router.delete("/{story_id}")
def delete_story(story_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_tables(c)
        row=c.execute("SELECT user_id FROM stories WHERE id=?",(story_id,)).fetchone()
        if not row: raise HTTPException(404,"Story not found")
        if row["user_id"] != uid: raise HTTPException(403,"You can only delete your own story")
        c.execute("DELETE FROM stories WHERE id=?",(story_id,)); c.execute("DELETE FROM story_views WHERE story_id=?",(story_id,))
    return {"ok":True}
