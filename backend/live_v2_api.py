from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from uuid import uuid4

from main import current_user, db

router = APIRouter(prefix="/api/live/v2", tags=["live-v2"])
REPLAY_STATUSES = {"recording", "processing", "ready", "failed"}
REPLAY_TRANSITIONS = {
    "recording": {"processing", "failed"},
    "processing": {"ready", "failed"},
    "ready": set(),
    "failed": {"processing"},
}


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
    c.execute("CREATE TABLE IF NOT EXISTS live_replays(id TEXT PRIMARY KEY,room_id TEXT NOT NULL,host_id TEXT NOT NULL,media_url TEXT,status TEXT NOT NULL DEFAULT 'processing',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,ended_at TEXT,duration_seconds INTEGER,bytes INTEGER,error_message TEXT)")
    for column, definition in (("updated_at", "TEXT"), ("ended_at", "TEXT"), ("duration_seconds", "INTEGER"), ("bytes", "INTEGER"), ("error_message", "TEXT")):
        try:
            c.execute(f"ALTER TABLE live_replays ADD COLUMN {column} {definition}")
        except Exception:
            pass
    c.execute("CREATE INDEX IF NOT EXISTS idx_live_replays_room_status ON live_replays(room_id,status,created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_live_replays_host ON live_replays(host_id,created_at)")


class ReplayIn(BaseModel):
    media_url: str = Field(default="", max_length=2000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    bytes: int | None = Field(default=None, ge=0)


class ReplayStatusIn(BaseModel):
    status: str
    media_url: str | None = Field(default=None, max_length=2000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    bytes: int | None = Field(default=None, ge=0)
    error_message: str | None = Field(default=None, max_length=1000)


def replay_dict(row):
    return dict(row) if row else None


def host_replay(c, room_id, uid, replay_id):
    row = c.execute("SELECT id,room_id,host_id,media_url,status,created_at,updated_at,ended_at,duration_seconds,bytes,error_message FROM live_replays WHERE id=? AND room_id=?", (replay_id, room_id)).fetchone()
    if not row:
        raise HTTPException(404, "Replay not found")
    if str(row[2]) != str(uid):
        raise HTTPException(403, "Only the LIVE host can manage the replay")
    return row


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
        replay = c.execute("SELECT id,status,media_url,duration_seconds,bytes,updated_at,error_message FROM live_replays WHERE room_id=? ORDER BY created_at DESC LIMIT 1", (room_id,)).fetchone()
        c.execute("UPDATE live_rooms SET viewer_count=? WHERE id=?", (active,room_id))
    return {"room": dict(room), "active_viewers": active, "messages": messages, "reactions": reactions, "accepted_guests": guests, "replay": replay_dict(replay)}


@router.post("/{room_id}/replay")
def create_replay(room_id: str, data: ReplayIn, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    media = data.media_url.strip()
    if not media:
        raise HTTPException(400, "Replay media URL required")
    with db() as c:
        ensure_tables(c)
        room = c.execute("SELECT user_id,status FROM live_rooms WHERE id=?", (room_id,)).fetchone()
        if not room or str(room[0]) != str(uid):
            raise HTTPException(403, "Only the LIVE host can create a replay")
        rid = uuid4().hex
        t = now()
        c.execute("INSERT INTO live_replays(id,room_id,host_id,media_url,status,created_at,updated_at,ended_at,duration_seconds,bytes,error_message) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (rid,room_id,uid,media,"ready",t,t,t,data.duration_seconds,data.bytes,None))
        row = c.execute("SELECT id,room_id,host_id,media_url,status,created_at,updated_at,ended_at,duration_seconds,bytes,error_message FROM live_replays WHERE id=?", (rid,)).fetchone()
    return {"replay": replay_dict(row)}


@router.post("/{room_id}/replay/start")
def start_replay(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_tables(c)
        room = c.execute("SELECT user_id,status FROM live_rooms WHERE id=?", (room_id,)).fetchone()
        if not room or str(room[0]) != str(uid):
            raise HTTPException(403, "Only the LIVE host can start recording")
        if room[1] != "live":
            raise HTTPException(409, "Replay recording can only start while LIVE is active")
        existing = c.execute("SELECT id,status FROM live_replays WHERE room_id=? AND status IN ('recording','processing') ORDER BY created_at DESC LIMIT 1", (room_id,)).fetchone()
        if existing:
            return {"replay_id": existing[0], "status": existing[1]}
        rid = uuid4().hex
        t = now()
        c.execute("INSERT INTO live_replays(id,room_id,host_id,media_url,status,created_at,updated_at,ended_at,duration_seconds,bytes,error_message) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (rid,room_id,uid,"","recording",t,t,None,None,None,None))
    return {"replay_id": rid, "room_id": room_id, "status": "recording"}


@router.post("/{room_id}/replay/{replay_id}/status")
def update_replay_status(room_id: str, replay_id: str, data: ReplayStatusIn, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    status = data.status.strip().lower()
    if status not in REPLAY_STATUSES:
        raise HTTPException(400, "Invalid replay status")
    if status == "ready" and not (data.media_url or "").strip():
        raise HTTPException(400, "media_url is required when replay is ready")
    with db() as c:
        ensure_tables(c)
        row = host_replay(c, room_id, uid, replay_id)
        current = str(row[4])
        if status != current and status not in REPLAY_TRANSITIONS.get(current, set()):
            raise HTTPException(409, f"Invalid replay transition: {current} -> {status}")
        t = now()
        ended = t if status in {"ready", "failed"} else row[7]
        media = data.media_url.strip() if data.media_url is not None else row[3]
        c.execute("UPDATE live_replays SET status=?,media_url=?,updated_at=?,ended_at=?,duration_seconds=?,bytes=?,error_message=? WHERE id=?", (status,media,t,ended,data.duration_seconds if data.duration_seconds is not None else row[8],data.bytes if data.bytes is not None else row[9],data.error_message if status == "failed" else None,replay_id))
        updated = c.execute("SELECT id,room_id,host_id,media_url,status,created_at,updated_at,ended_at,duration_seconds,bytes,error_message FROM live_replays WHERE id=?", (replay_id,)).fetchone()
    return {"replay": replay_dict(updated)}


@router.get("/{room_id}/replay")
def get_replay(room_id: str):
    with db() as c:
        ensure_tables(c)
        row = c.execute("SELECT id,room_id,host_id,media_url,status,created_at,updated_at,ended_at,duration_seconds,bytes,error_message FROM live_replays WHERE room_id=? ORDER BY created_at DESC LIMIT 1", (room_id,)).fetchone()
    return {"replay": replay_dict(row)}
