from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from main import current_user, db

router = APIRouter(prefix="/api/live", tags=["live-moderation"])


def uid_from(auth):
    uid = current_user(auth)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def now():
    return datetime.now(timezone.utc).isoformat()


def ensure_table(c):
    c.execute("""CREATE TABLE IF NOT EXISTS live_moderation (
        room_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        value TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(room_id,user_id,action)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS live_pins (
        room_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL,
        pinned_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")


def require_host(c, room_id, uid):
    row = c.execute("SELECT user_id,status FROM live_rooms WHERE id=?", (room_id,)).fetchone()
    if not row or str(row[0]) != str(uid) or row[1] != "live":
        raise HTTPException(403, "Host permission required")


class Action(BaseModel):
    action: str
    value: str | None = None


@router.post("/{room_id}/moderation")
def moderate(room_id: str, data: Action, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    action = data.action.strip().lower()
    if action not in {"mute", "block", "kick"}:
        raise HTTPException(400, "Invalid moderation action")
    target = str(data.value or "").strip()
    if not target or target == str(uid):
        raise HTTPException(400, "Invalid target")
    with db() as c:
        ensure_table(c)
        require_host(c, room_id, uid)
        t = now()
        c.execute("INSERT INTO live_moderation(room_id,user_id,action,value,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(room_id,user_id,action) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (room_id,target,action,"1",t,t))
        return {"ok": True, "action": action, "user_id": target}


@router.delete("/{room_id}/moderation/{action}/{user_id}")
def clear_moderation(room_id: str, action: str, user_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    action = action.strip().lower()
    with db() as c:
        ensure_table(c)
        require_host(c, room_id, uid)
        c.execute("DELETE FROM live_moderation WHERE room_id=? AND user_id=? AND action=?", (room_id,user_id,action))
        return {"ok": True}


@router.get("/{room_id}/moderation")
def get_moderation(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_table(c)
        rows = c.execute("SELECT user_id,action,value,created_at FROM live_moderation WHERE room_id=? AND (user_id=? OR ?=(SELECT user_id FROM live_rooms WHERE id=?))", (room_id,uid,uid,room_id)).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/{room_id}/pin")
def pin_comment(room_id: str, message_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    message_id = str(message_id).strip()
    if not message_id:
        raise HTTPException(400, "Message ID required")
    with db() as c:
        ensure_table(c)
        require_host(c, room_id, uid)
        c.execute("INSERT INTO live_pins(room_id,message_id,pinned_by,created_at) VALUES(?,?,?,?) ON CONFLICT(room_id) DO UPDATE SET message_id=excluded.message_id,pinned_by=excluded.pinned_by,created_at=excluded.created_at", (room_id,message_id,uid,now()))
        return {"ok": True, "message_id": message_id}


@router.delete("/{room_id}/pin")
def unpin_comment(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_table(c)
        require_host(c, room_id, uid)
        c.execute("DELETE FROM live_pins WHERE room_id=?", (room_id,))
        return {"ok": True}


@router.get("/{room_id}/pin")
def get_pin(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_table(c)
        row = c.execute("SELECT message_id,pinned_by,created_at FROM live_pins WHERE room_id=?", (room_id,)).fetchone()
        return {"pinned": dict(row) if row else None}
