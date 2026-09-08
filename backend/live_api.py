from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone

from main import current_user, db

router = APIRouter(prefix="/api/live", tags=["live"])


def require_user(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS live_rooms(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'live', viewer_count INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, ended_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS live_messages(id TEXT PRIMARY KEY, room_id TEXT NOT NULL, user_id TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS live_reactions(id TEXT PRIMARY KEY, room_id TEXT NOT NULL, user_id TEXT NOT NULL, reaction TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_live_rooms_status ON live_rooms(status,created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_live_messages_room ON live_messages(room_id,created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_live_reactions_room ON live_reactions(room_id,created_at)")


class LiveCreate(BaseModel):
    title: str = "Live on REelo"


class LiveMessage(BaseModel):
    message: str


class LiveReaction(BaseModel):
    reaction: str = "❤️"


@router.post("")
def start_live(data: LiveCreate, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    title = data.title.strip()[:120] or "Live on REelo"
    room_id = uuid4().hex
    with db() as c:
        ensure_tables(c)
        c.execute("UPDATE live_rooms SET status='ended',ended_at=? WHERE user_id=? AND status='live'", (datetime.now(timezone.utc).isoformat(), uid))
        c.execute("INSERT INTO live_rooms(id,user_id,title) VALUES(?,?,?)", (room_id, uid, title))
    return {"id": room_id, "title": title, "status": "live", "viewer_count": 0}


@router.get("")
def list_live(limit: int = 30):
    limit = max(1, min(limit, 100))
    with db() as c:
        ensure_tables(c)
        rows = c.execute("SELECT r.*,u.username,u.display_name FROM live_rooms r JOIN users u ON u.id=r.user_id WHERE r.status='live' ORDER BY r.created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/{room_id}")
def live_detail(room_id: str):
    with db() as c:
        ensure_tables(c)
        row = c.execute("SELECT r.*,u.username,u.display_name FROM live_rooms r JOIN users u ON u.id=r.user_id WHERE r.id=?", (room_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Live room not found")
        messages = c.execute("SELECT m.*,u.username,u.display_name FROM live_messages m JOIN users u ON u.id=m.user_id WHERE m.room_id=? ORDER BY m.created_at DESC LIMIT 100", (room_id,)).fetchall()
    return {"room": dict(row), "messages": [dict(x) for x in reversed(messages)]}


@router.post("/{room_id}/join")
def join_live(room_id: str, authorization: str | None = Header(default=None)):
    require_user(authorization)
    with db() as c:
        ensure_tables(c)
        cur = c.execute("UPDATE live_rooms SET viewer_count=viewer_count+1 WHERE id=? AND status='live'", (room_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Live is not active")
        row = c.execute("SELECT viewer_count FROM live_rooms WHERE id=?", (room_id,)).fetchone()
    return {"ok": True, "viewer_count": row[0]}


@router.post("/{room_id}/leave")
def leave_live(room_id: str, authorization: str | None = Header(default=None)):
    require_user(authorization)
    with db() as c:
        ensure_tables(c)
        c.execute("UPDATE live_rooms SET viewer_count=MAX(viewer_count-1,0) WHERE id=?", (room_id,))
        row = c.execute("SELECT viewer_count FROM live_rooms WHERE id=?", (room_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Live room not found")
    return {"ok": True, "viewer_count": row[0]}


@router.post("/{room_id}/end")
def end_live(room_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_tables(c)
        cur = c.execute("UPDATE live_rooms SET status='ended',ended_at=? WHERE id=? AND user_id=? AND status='live'", (datetime.now(timezone.utc).isoformat(), room_id, uid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Live room not found or already ended")
    return {"ok": True, "status": "ended"}


@router.post("/{room_id}/messages")
def send_message(room_id: str, data: LiveMessage, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    text = data.message.strip()
    if not text or len(text) > 300:
        raise HTTPException(400, "Message must be 1-300 characters")
    mid = uuid4().hex
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT id FROM live_rooms WHERE id=? AND status='live'", (room_id,)).fetchone():
            raise HTTPException(404, "Live is not active")
        c.execute("INSERT INTO live_messages(id,room_id,user_id,message) VALUES(?,?,?,?)", (mid, room_id, uid, text))
        row = c.execute("SELECT m.*,u.username,u.display_name FROM live_messages m JOIN users u ON u.id=m.user_id WHERE m.id=?", (mid,)).fetchone()
    return dict(row)


@router.get("/{room_id}/messages")
def get_messages(room_id: str, after: str = ""):
    with db() as c:
        ensure_tables(c)
        if after:
            rows = c.execute("SELECT m.*,u.username,u.display_name FROM live_messages m JOIN users u ON u.id=m.user_id WHERE m.room_id=? AND m.created_at>? ORDER BY m.created_at ASC LIMIT 100", (room_id, after)).fetchall()
        else:
            rows = c.execute("SELECT m.*,u.username,u.display_name FROM live_messages m JOIN users u ON u.id=m.user_id WHERE m.room_id=? ORDER BY m.created_at DESC LIMIT 100", (room_id,)).fetchall()
    return {"items": [dict(x) for x in reversed(rows)]}


@router.post("/{room_id}/reactions")
def react(room_id: str, data: LiveReaction, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    reaction = data.reaction.strip()[:16] or "❤️"
    rid = uuid4().hex
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT id FROM live_rooms WHERE id=? AND status='live'", (room_id,)).fetchone():
            raise HTTPException(404, "Live is not active")
        c.execute("INSERT INTO live_reactions(id,room_id,user_id,reaction) VALUES(?,?,?,?)", (rid, room_id, uid, reaction))
    return {"ok": True, "reaction": reaction}


@router.get("/{room_id}/reactions")
def reaction_stats(room_id: str):
    with db() as c:
        ensure_tables(c)
        rows = c.execute("SELECT reaction,COUNT(*) count FROM live_reactions WHERE room_id=? GROUP BY reaction ORDER BY count DESC", (room_id,)).fetchall()
    return {"items": [dict(x) for x in rows]}
