from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from pathlib import Path
from uuid import uuid4
import json

from main import current_user, db, MEDIA, MAX_VIDEO_BYTES

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


def require_user(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_table(c):
    c.execute("""CREATE TABLE IF NOT EXISTS drafts(
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT NOT NULL,
        caption TEXT DEFAULT '', settings TEXT DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_drafts_user_updated ON drafts(user_id, updated_at DESC)")


@router.post("")
async def save_draft(
    file: UploadFile = File(...),
    draft_id: str = Form(""),
    caption: str = Form(""),
    settings: str = Form("{}"),
    authorization: str | None = Header(default=None),
):
    uid = require_user(authorization)
    ext = Path(file.filename or "video.mp4").suffix.lower()
    if ext not in {".mp4", ".mov", ".webm", ".m4v"}:
        raise HTTPException(415, "Unsupported video format")
    try:
        parsed = json.loads(settings or "{}")
        if not isinstance(parsed, dict):
            raise ValueError()
    except ValueError:
        raise HTTPException(400, "Invalid draft settings")

    did = draft_id.strip() or uuid4().hex
    with db() as c:
        ensure_table(c)
        old = c.execute("SELECT filename FROM drafts WHERE id=? AND user_id=?", (did, uid)).fetchone()
        if old:
            filename = old["filename"]
        else:
            filename = f"draft-{uuid4().hex}{ext}"

        path = MEDIA / filename
        total = 0
        with path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    path.unlink(missing_ok=True)
                    raise HTTPException(413, "Video is too large. Maximum size is 100 MB.")
                out.write(chunk)
        if not total:
            path.unlink(missing_ok=True)
            raise HTTPException(400, "Empty video file")

        c.execute("""INSERT INTO drafts(id,user_id,filename,caption,settings,updated_at)
                     VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
                     ON CONFLICT(id) DO UPDATE SET filename=excluded.filename,caption=excluded.caption,
                     settings=excluded.settings,updated_at=CURRENT_TIMESTAMP""",
                  (did, uid, filename, caption.strip()[:2200], json.dumps(parsed)))

    return {"id": did, "url": f"/media/{filename}", "caption": caption.strip()[:2200], "settings": parsed}


@router.get("")
def list_drafts(authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        rows = c.execute("SELECT id,filename,caption,settings,created_at,updated_at FROM drafts WHERE user_id=? ORDER BY updated_at DESC LIMIT 50", (uid,)).fetchall()
    items = []
    for r in rows:
        try: settings = json.loads(r["settings"] or "{}")
        except Exception: settings = {}
        items.append({**dict(r), "settings": settings, "url": f"/media/{r['filename']}"})
    return {"items": items}


@router.get("/{draft_id}")
def get_draft(draft_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        r = c.execute("SELECT id,filename,caption,settings,created_at,updated_at FROM drafts WHERE id=? AND user_id=?", (draft_id, uid)).fetchone()
    if not r:
        raise HTTPException(404, "Draft not found")
    try: settings = json.loads(r["settings"] or "{}")
    except Exception: settings = {}
    return {**dict(r), "settings": settings, "url": f"/media/{r['filename']}"}


@router.delete("/{draft_id}")
def delete_draft(draft_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        r = c.execute("SELECT filename FROM drafts WHERE id=? AND user_id=?", (draft_id, uid)).fetchone()
        if not r:
            raise HTTPException(404, "Draft not found")
        c.execute("DELETE FROM drafts WHERE id=? AND user_id=?", (draft_id, uid))
    (MEDIA / r["filename"]).unlink(missing_ok=True)
    return {"ok": True}
