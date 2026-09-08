from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4

from main import current_user, db

router = APIRouter(prefix="/api/live/v2", tags=["live-v2"])


def uid_from(auth):
    uid = current_user(auth)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def now():
    return datetime.now(timezone.utc).isoformat()


def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS live_viewers(room_id TEXT NOT NULL,user_id TEXT NOT NULL,joined_at TEXT NOT NULL,last_seen_at TEXT NOT NULL,left_at TEXT,PRIMARY KEY(room_id,user_id))")
    c.execute("CREATE INDEX IF NOT EXISTS idx_live_viewers_room ON live_viewers(room_id,left_at,last_seen_at)")
    c.execute("CREATE TABLE IF NOT EXISTS live_replays(id TEXT PRIMARY KEY,room_id TEXT NOT NULL,host_id TEXT NOT NULL,media_url TEXT,status TEXT NOT NULL DEFAULT 'processing',created_at TEXT NOT NULL)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_live_replays_host ON live_replays(host_id,created_at)")


class ReplayIn(BaseModel):
    media_url: str


@router.post("/{room_id}/presence")
def presence(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    t = now()
    with db() as c:
        ensure_tables(c)
        room = c.execute("SELECT id,status FROM live_rooms WHERE id=?", (room_id,)).fetchone()
        if not room or room[1] != "live":
            raise HTTPException(404, "Live is not active")
        c.execute("INSERT INTO live_viewers(room_id,user_id,joined_at,last_seen_at,left_at) VALUES(?,?,?,?,NULL) ON CONFLICT(room_id,user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at,left_at=NULL", (room_id,uid,t,t))
        count = c.execute("SELECT COUNT(*) FROM live_viewers WHERE room_id=? AND left_at IS NULL AND last_seen_at>=datetime('now','-45 seconds')", (room_id,)).fetchone()[0]
        c.execute("UPDATE live_rooms SET viewer_count=? WHERE id=?", (count,room_id))
    return {"ok": True, "viewer_count": count}


@router.post("/{room_id}/leave")
def presence_leave(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_tables(c)
        c.execute("UPDATE live_viewers SET left_at=?,last_seen_at=? WHERE room_id=? AND user_id=? AND left_at IS NULL", (now(),now(),room_id,uid))
        count = c.execute("SELECT COUNT(*) FROM live_viewers WHERE room_id=? AND left_at IS NULL AND last_seen_at>=datetime('now','-45 seconds')", (room_id,)).fetchone()[0]
        c.execute("UPDATE live_rooms SET viewer_count=? WHERE id=?", (count,room_id))
    return {"ok": True, "viewer_count": count}


@router.get("/{room_id}/stats")
def live_stats(room_id: str, authorization: str | None = Header(default=None)):
    uid_from(authorization)
    with db() as c:
        ensure_tables(c)
        room = c.execute("SELECT id,user_id,title,status,viewer_count,created_at,ended_at FROM live_rooms WHERE id=?", (room_id,)).fetchone()
        if not room:
            raise HTTPException(404, "Live room not found")
        active = c.execute("SELECT COUNT(*) FROM live_viewers WHERE room_id=? AND left_at IS NULL AND last_seen_at>=datetime('now','-45 seconds')", (room_id,)).fetchone()[0]
        reactions = c.execute("SELECT COUNT(*) FROM live_reactions WHERE room_id=?", (room_id,)).fetchone()[0]
        messages = c.execute("SELECT COUNT(*) FROM live_messages WHERE room_id=?", (room_id,)).fetchone()[0]
        guests = c.execute("SELECT COUNT(*) FROM live_guests WHERE room_id=? AND status='accepted'", (room_id,)).fetchone()[0]
        c.execute("UPDATE live_rooms SET viewer_count=? WHERE id=?", (active,room_id))
    return {"room": dict(room), "active_viewers": active, "messages": messages, "reactions": reactions, "accepted_guests": guests}


@router.post("/{room_id}/replay")
def create_replay(room_id: str, data: ReplayIn, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    media = data.media_url.strip()
    if not media or len(media) > 2000:
        raise HTTPException(400, "Valid replay media URL required")
    with db() as c:
        ensure_tables(c)
        room = c.execute("SELECT user_id FROM live_rooms WHERE id=?", (room_id,)).fetchone()
        if not room or str(room[0]) != str(uid):
            raise HTTPException(403, "Only the LIVE host can create a replay")
        rid = uuid4().hex
        c.execute("INSERT INTO live_replays(id,room_id,host_id,media_url,status,created_at) VALUES(?,?,?,?,?,?)", (rid,room_id,uid,media,"ready",now()))
    return {"id": rid, "room_id": room_id, "media_url": media, "status": "ready"}


@router.get("/{room_id}/replay")
def get_replay(room_id: str):
    with db() as c:
        ensure_tables(c)
        row = c.execute("SELECT id,room_id,host_id,media_url,status,created_at FROM live_replays WHERE room_id=? ORDER BY created_at DESC LIMIT 1", (room_id,)).fetchone()
    return {"replay": dict(row) if row else None}
