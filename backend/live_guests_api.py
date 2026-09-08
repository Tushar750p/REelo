from datetime import datetime, timezone
import sqlite3

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from main import current_user, db

router = APIRouter(prefix="/api/live", tags=["live-guests"])


def uid_from(auth):
    uid = current_user(auth)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def now():
    return datetime.now(timezone.utc).isoformat()


def ensure_table(c):
    c.execute("""CREATE TABLE IF NOT EXISTS live_guests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT NOT NULL,
        host_id TEXT NOT NULL,
        guest_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'invited',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(room_id, guest_id)
    )""")


class GuestRequest(BaseModel):
    user_id: str


@router.post("/{room_id}/guests/invite")
def invite_guest(room_id: str, data: GuestRequest, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    guest_id = str(data.user_id).strip()
    if not guest_id or guest_id == str(uid):
        raise HTTPException(400, "Invalid guest")
    with db() as c:
        ensure_table(c)
        room = c.execute("SELECT user_id,status FROM live_rooms WHERE id=?", (room_id,)).fetchone()
        if not room or str(room[0]) != str(uid) or room[1] != "live":
            raise HTTPException(403, "Only the LIVE host can invite guests")
        exists = c.execute("SELECT id FROM users WHERE id=?", (guest_id,)).fetchone()
        if not exists:
            raise HTTPException(404, "Guest user not found")
        count = c.execute("SELECT COUNT(*) FROM live_guests WHERE room_id=? AND status IN ('invited','accepted')", (room_id,)).fetchone()[0]
        if count >= 3:
            raise HTTPException(409, "Maximum guest slots reached")
        t = now()
        c.execute("INSERT INTO live_guests(room_id,host_id,guest_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(room_id,guest_id) DO UPDATE SET status='invited',updated_at=excluded.updated_at", (room_id,uid,guest_id,"invited",t,t))
        return {"ok": True, "status": "invited", "guest_id": guest_id}


@router.get("/{room_id}/guests")
def list_guests(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_table(c)
        rows = c.execute("SELECT id,host_id,guest_id,status,created_at,updated_at FROM live_guests WHERE room_id=? AND (host_id=? OR guest_id=?) ORDER BY id", (room_id,uid,uid)).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/{room_id}/guests/accept")
def accept_guest(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_table(c)
        row = c.execute("SELECT id FROM live_guests WHERE room_id=? AND guest_id=? AND status='invited'", (room_id,uid)).fetchone()
        if not row:
            raise HTTPException(404, "Guest invitation not found")
        c.execute("UPDATE live_guests SET status='accepted',updated_at=? WHERE id=?", (now(),row[0]))
        return {"ok": True, "status": "accepted", "room": room_id, "role": "guest"}


@router.post("/{room_id}/guests/decline")
def decline_guest(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_table(c)
        row = c.execute("SELECT id FROM live_guests WHERE room_id=? AND guest_id=? AND status='invited'", (room_id,uid)).fetchone()
        if not row:
            raise HTTPException(404, "Guest invitation not found")
        c.execute("UPDATE live_guests SET status='declined',updated_at=? WHERE id=?", (now(),row[0]))
        return {"ok": True, "status": "declined"}


@router.post("/{room_id}/guests/remove/{guest_id}")
def remove_guest(room_id: str, guest_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_table(c)
        row = c.execute("SELECT id FROM live_guests WHERE room_id=? AND host_id=? AND guest_id=?", (room_id,uid,guest_id)).fetchone()
        if not row:
            raise HTTPException(404, "Guest not found")
        c.execute("UPDATE live_guests SET status='removed',updated_at=? WHERE id=?", (now(),row[0]))
        return {"ok": True, "status": "removed"}
