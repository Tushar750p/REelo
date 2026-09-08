from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4

from main import current_user, db

router = APIRouter(prefix="/api/sounds", tags=["sounds"])


def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS sounds(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, title TEXT NOT NULL, artist TEXT DEFAULT '', audio_url TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS video_sounds(video_id TEXT PRIMARY KEY, sound_id TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_video_sounds_sound ON video_sounds(sound_id)")


def require_user(a):
    uid = current_user(a)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


class SoundIn(BaseModel):
    title: str
    artist: str = ""
    audio_url: str


@router.post("")
def create_sound(data: SoundIn, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    title, artist, audio = data.title.strip(), data.artist.strip(), data.audio_url.strip()
    if not title or len(title) > 120 or len(artist) > 120 or not audio or len(audio) > 1000:
        raise HTTPException(400, "Invalid sound data")
    sid = uuid4().hex
    with db() as c:
        ensure_tables(c)
        c.execute("INSERT INTO sounds(id,owner_id,title,artist,audio_url) VALUES(?,?,?,?,?)", (sid, uid, title, artist, audio))
    return {"id": sid, "title": title, "artist": artist, "audio_url": audio, "video_count": 0}


@router.get("")
def list_sounds(q: str = "", limit: int = 30):
    limit = max(1, min(limit, 100))
    q = q.strip()
    with db() as c:
        ensure_tables(c)
        if q:
            rows = c.execute("SELECT s.*,u.username,(SELECT COUNT(*) FROM video_sounds vs WHERE vs.sound_id=s.id) video_count FROM sounds s JOIN users u ON u.id=s.owner_id WHERE s.title LIKE ? OR s.artist LIKE ? ORDER BY video_count DESC,s.created_at DESC LIMIT ?", (f"%{q}%", f"%{q}%", limit)).fetchall()
        else:
            rows = c.execute("SELECT s.*,u.username,(SELECT COUNT(*) FROM video_sounds vs WHERE vs.sound_id=s.id) video_count FROM sounds s JOIN users u ON u.id=s.owner_id ORDER BY video_count DESC,s.created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/{sound_id}/use")
def use_sound(sound_id: str, video_id: str, authorization: str | None = Header(default=None)):
    require_user(authorization)
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT id FROM sounds WHERE id=?", (sound_id,)).fetchone():
            raise HTTPException(404, "Sound not found")
        if not c.execute("SELECT id FROM videos WHERE id=?", (video_id,)).fetchone():
            raise HTTPException(404, "Video not found")
        c.execute("INSERT OR REPLACE INTO video_sounds(video_id,sound_id) VALUES(?,?)", (video_id, sound_id))
    return {"ok": True, "sound_id": sound_id, "video_id": video_id}


@router.get("/{sound_id}")
def sound_detail(sound_id: str):
    with db() as c:
        ensure_tables(c)
        row = c.execute("SELECT s.*,u.username,(SELECT COUNT(*) FROM video_sounds vs WHERE vs.sound_id=s.id) video_count FROM sounds s JOIN users u ON u.id=s.owner_id WHERE s.id=?", (sound_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Sound not found")
        videos = c.execute("SELECT v.*,u.username,u.display_name FROM videos v JOIN video_sounds vs ON vs.video_id=v.id JOIN users u ON u.id=v.user_id WHERE vs.sound_id=? AND v.status='ready' ORDER BY v.created_at DESC LIMIT 50", (sound_id,)).fetchall()
    return {"sound": dict(row), "videos": [dict(v) for v in videos]}
