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
    c.execute("CREATE TABLE IF NOT EXISTS story_reactions(story_id TEXT NOT NULL,user_id TEXT NOT NULL,reaction TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(story_id,user_id))")
    c.execute("CREATE TABLE IF NOT EXISTS story_replies(id TEXT PRIMARY KEY,story_id TEXT NOT NULL,user_id TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stories_expiry ON stories(expires_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_story_views_story ON story_views(story_id,viewed_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_story_replies_story ON story_replies(story_id,created_at)")


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')


def visible_story(c, story_id, uid):
    row = c.execute("SELECT s.*,u.username,u.display_name FROM stories s JOIN users u ON u.id=s.user_id WHERE s.id=?", (story_id,)).fetchone()
    if not row:
        return None
    if row["user_id"] == uid:
        return row
    # Private accounts expose stories only to followers.
    cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
    if "private_account" in cols:
        private = c.execute("SELECT private_account FROM users WHERE id=?", (row["user_id"],)).fetchone()
        if private and private[0]:
            if not c.execute("SELECT 1 FROM follows WHERE follower_id=? AND following_id=?", (uid,row["user_id"])).fetchone():
                return None
    return row


class StoryIn(BaseModel):
    media_url: str
    caption: str = ""


class StoryReplyIn(BaseModel):
    body: str


class StoryReactionIn(BaseModel):
    reaction: str


@router.get("")
def list_stories(authorization: str | None = Header(default=None), limit: int = 100):
    uid = require_user(authorization)
    now = now_iso()
    limit = max(1, min(limit, 100))
    with db() as c:
        ensure_tables(c)
        rows = c.execute("""
            SELECT s.*,u.username,u.display_name,
                   CASE WHEN sv.user_id IS NULL THEN 0 ELSE 1 END viewed,
                   (SELECT COUNT(*) FROM story_views x WHERE x.story_id=s.id) views,
                   (SELECT COUNT(*) FROM story_reactions sr WHERE sr.story_id=s.id) reactions,
                   (SELECT reaction FROM story_reactions mr WHERE mr.story_id=s.id AND mr.user_id=? LIMIT 1) my_reaction
            FROM stories s JOIN users u ON u.id=s.user_id
            LEFT JOIN story_views sv ON sv.story_id=s.id AND sv.user_id=?
            WHERE s.expires_at>? AND (s.user_id=? OR NOT EXISTS (SELECT 1 FROM pragma_table_info('users') WHERE name='private_account') OR COALESCE((SELECT private_account FROM users pu WHERE pu.id=s.user_id),0)=0 OR EXISTS (SELECT 1 FROM follows f WHERE f.follower_id=? AND f.following_id=s.user_id))
            ORDER BY viewed ASC,s.created_at DESC LIMIT ?
        """,(uid,uid,now,uid,uid,limit)).fetchall()
    return {"items":[dict(r) for r in rows],"version":"2.0"}


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
    return {"id":sid,"media_url":media,"caption":caption,"expires_at":expires,"version":"2.0"}


@router.get("/{story_id}")
def story_detail(story_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    now = now_iso()
    with db() as c:
        ensure_tables(c)
        row = visible_story(c,story_id,uid)
        if not row or row["expires_at"] <= now:
            raise HTTPException(404,"Story not found")
        data = dict(row)
        data["views"] = c.execute("SELECT COUNT(*) FROM story_views WHERE story_id=?",(story_id,)).fetchone()[0]
        data["reactions"] = c.execute("SELECT COUNT(*) FROM story_reactions WHERE story_id=?",(story_id,)).fetchone()[0]
        data["my_reaction"] = (c.execute("SELECT reaction FROM story_reactions WHERE story_id=? AND user_id=?",(story_id,uid)).fetchone() or [None])[0]
        data["reply_count"] = c.execute("SELECT COUNT(*) FROM story_replies WHERE story_id=?",(story_id,)).fetchone()[0]
    return data


@router.post("/{story_id}/view")
def view_story(story_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    now = now_iso()
    with db() as c:
        ensure_tables(c)
        row = visible_story(c,story_id,uid)
        if not row or row["expires_at"] <= now: raise HTTPException(404,"Story not found")
        c.execute("INSERT OR IGNORE INTO story_views(story_id,user_id) VALUES(?,?)",(story_id,uid))
    return {"ok":True}


@router.get("/{story_id}/viewers")
def story_viewers(story_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_tables(c)
        row=c.execute("SELECT user_id FROM stories WHERE id=?",(story_id,)).fetchone()
        if not row: raise HTTPException(404,"Story not found")
        if row["user_id"] != uid: raise HTTPException(403,"Only the story owner can see viewers")
        rows=c.execute("SELECT u.id user_id,u.username,u.display_name,sv.viewed_at FROM story_views sv JOIN users u ON u.id=sv.user_id WHERE sv.story_id=? ORDER BY sv.viewed_at DESC",(story_id,)).fetchall()
    return {"items":[dict(r) for r in rows],"count":len(rows)}


@router.post("/{story_id}/reaction")
def react_story(story_id: str, data: StoryReactionIn, authorization: str | None = Header(default=None)):
    uid=require_user(authorization); reaction=data.reaction.strip().lower()
    allowed={"like","love","laugh","wow","sad","fire"}
    if reaction not in allowed: raise HTTPException(400,"Unsupported reaction")
    with db() as c:
        ensure_tables(c)
        row=visible_story(c,story_id,uid)
        if not row or row["expires_at"] <= now_iso(): raise HTTPException(404,"Story not found")
        c.execute("INSERT INTO story_reactions(story_id,user_id,reaction) VALUES(?,?,?) ON CONFLICT(story_id,user_id) DO UPDATE SET reaction=excluded.reaction,created_at=CURRENT_TIMESTAMP",(story_id,uid,reaction))
    return {"ok":True,"reaction":reaction}


@router.delete("/{story_id}/reaction")
def remove_reaction(story_id: str, authorization: str | None = Header(default=None)):
    uid=require_user(authorization)
    with db() as c:
        ensure_tables(c); c.execute("DELETE FROM story_reactions WHERE story_id=? AND user_id=?",(story_id,uid))
    return {"ok":True}


@router.post("/{story_id}/reply")
def reply_story(story_id: str, data: StoryReplyIn, authorization: str | None = Header(default=None)):
    uid=require_user(authorization); body=data.body.strip()
    if not body or len(body)>1000: raise HTTPException(400,"Reply must be 1-1000 characters")
    with db() as c:
        ensure_tables(c); row=visible_story(c,story_id,uid)
        if not row or row["expires_at"] <= now_iso(): raise HTTPException(404,"Story not found")
        rid=uuid4().hex
        c.execute("INSERT INTO story_replies(id,story_id,user_id,body) VALUES(?,?,?,?)",(rid,story_id,uid,body))
        r=c.execute("SELECT sr.id,sr.body,sr.created_at,u.id user_id,u.username,u.display_name FROM story_replies sr JOIN users u ON u.id=sr.user_id WHERE sr.id=?",(rid,)).fetchone()
    return {"ok":True,"reply":dict(r)}


@router.get("/{story_id}/replies")
def story_replies(story_id: str, limit: int=50, before: str|None=None, authorization: str|None=Header(default=None)):
    uid=require_user(authorization); limit=max(1,min(limit,100))
    with db() as c:
        ensure_tables(c); row=visible_story(c,story_id,uid)
        if not row: raise HTTPException(404,"Story not found")
        params=[story_id]; where="sr.story_id=?"
        if before: where += " AND sr.created_at < ?"; params.append(before)
        params.append(limit)
        rows=c.execute(f"SELECT sr.id,sr.body,sr.created_at,u.id user_id,u.username,u.display_name FROM story_replies sr JOIN users u ON u.id=sr.user_id WHERE {where} ORDER BY sr.created_at DESC LIMIT ?",params).fetchall()
    return {"items":[dict(r) for r in reversed(rows)],"limit":limit,"before":before}


@router.delete("/{story_id}")
def delete_story(story_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_tables(c)
        row=c.execute("SELECT user_id FROM stories WHERE id=?",(story_id,)).fetchone()
        if not row: raise HTTPException(404,"Story not found")
        if row["user_id"] != uid: raise HTTPException(403,"You can only delete your own story")
        c.execute("DELETE FROM stories WHERE id=?",(story_id,)); c.execute("DELETE FROM story_views WHERE story_id=?",(story_id,)); c.execute("DELETE FROM story_reactions WHERE story_id=?",(story_id,)); c.execute("DELETE FROM story_replies WHERE story_id=?",(story_id,))
    return {"ok":True}
