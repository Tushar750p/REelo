from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from main import db, current_user

router = APIRouter(prefix="/api/saves", tags=["saves"])

class CollectionIn(BaseModel):
    name: str
    description: str | None = None
    is_private: bool = True

class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_private: bool | None = None


def require_user(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def init_tables():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS saved_videos(
            user_id TEXT NOT NULL,
            video_id TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, video_id)
        );
        CREATE TABLE IF NOT EXISTS save_collections(
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_private INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS collection_items(
            collection_id TEXT NOT NULL,
            video_id TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(collection_id, video_id)
        );
        """)


@router.on_event("startup")
def startup_saves():
    init_tables()


@router.post("/video/{video_id}")
def save_video(video_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        if not c.execute("SELECT 1 FROM videos WHERE id=? AND status='ready'", (video_id,)).fetchone():
            raise HTTPException(404, "Video not found")
        c.execute("INSERT OR IGNORE INTO saved_videos(user_id,video_id) VALUES(?,?)", (uid, video_id))
    return {"saved": True, "video_id": video_id}


@router.delete("/video/{video_id}")
def unsave_video(video_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        c.execute("DELETE FROM saved_videos WHERE user_id=? AND video_id=?", (uid, video_id))
        c.execute("DELETE FROM collection_items WHERE video_id=? AND collection_id IN (SELECT id FROM save_collections WHERE user_id=?)", (video_id, uid))
    return {"saved": False, "video_id": video_id}


@router.get("")
def saved_videos(limit: int = 50, offset: int = 0, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    with db() as c:
        rows = c.execute("""
            SELECT v.*, u.username, u.display_name, 1 AS saved,
                   CASE WHEN l.user_id IS NULL THEN 0 ELSE 1 END AS liked
            FROM saved_videos s
            JOIN videos v ON v.id=s.video_id
            JOIN users u ON u.id=v.user_id
            LEFT JOIN likes l ON l.video_id=v.id AND l.user_id=?
            WHERE s.user_id=? AND v.status='ready'
            ORDER BY s.created_at DESC LIMIT ? OFFSET ?
        """, (uid, uid, limit, offset)).fetchall()
        total = c.execute("SELECT COUNT(*) FROM saved_videos s JOIN videos v ON v.id=s.video_id WHERE s.user_id=? AND v.status='ready'", (uid,)).fetchone()[0]
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset, "has_more": offset + len(rows) < total}


@router.get("/video/{video_id}")
def saved_state(video_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        saved = bool(c.execute("SELECT 1 FROM saved_videos WHERE user_id=? AND video_id=?", (uid, video_id)).fetchone())
    return {"saved": saved, "video_id": video_id}


@router.post("/collections")
def create_collection(data: CollectionIn, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    name = data.name.strip()
    description = (data.description or "").strip()
    if not name or len(name) > 60:
        raise HTTPException(400, "Collection name must be 1-60 characters")
    if len(description) > 180:
        raise HTTPException(400, "Collection description must be 180 characters or less")
    cid = uuid4().hex
    with db() as c:
        c.execute("INSERT INTO save_collections(id,user_id,name,description,is_private) VALUES(?,?,?,?,?)", (cid, uid, name, description, 1 if data.is_private else 0))
    return {"id": cid, "name": name, "description": description, "is_private": bool(data.is_private), "items": 0}


@router.get("/collections")
def collections(authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        rows = c.execute("""
            SELECT c.*, COUNT(ci.video_id) AS items
            FROM save_collections c
            LEFT JOIN collection_items ci ON ci.collection_id=c.id
            WHERE c.user_id=?
            GROUP BY c.id
            ORDER BY c.updated_at DESC, c.created_at DESC
        """, (uid,)).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.patch("/collections/{collection_id}")
def update_collection(collection_id: str, data: CollectionUpdate, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        col = c.execute("SELECT * FROM save_collections WHERE id=? AND user_id=?", (collection_id, uid)).fetchone()
        if not col:
            raise HTTPException(404, "Collection not found")
        name = col["name"] if data.name is None else data.name.strip()
        description = col["description"] if data.description is None else (data.description or "").strip()
        is_private = int(col["is_private"] or 0) if data.is_private is None else (1 if data.is_private else 0)
        if not name or len(name) > 60:
            raise HTTPException(400, "Collection name must be 1-60 characters")
        if len(description) > 180:
            raise HTTPException(400, "Collection description must be 180 characters or less")
        c.execute("UPDATE save_collections SET name=?, description=?, is_private=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (name, description, is_private, collection_id, uid))
        updated = c.execute("SELECT * FROM save_collections WHERE id=?", (collection_id,)).fetchone()
    return {"collection": dict(updated)}


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        if not c.execute("SELECT 1 FROM save_collections WHERE id=? AND user_id=?", (collection_id, uid)).fetchone():
            raise HTTPException(404, "Collection not found")
        c.execute("DELETE FROM collection_items WHERE collection_id=?", (collection_id,))
        c.execute("DELETE FROM save_collections WHERE id=? AND user_id=?", (collection_id, uid))
    return {"deleted": True, "collection_id": collection_id}


@router.post("/collections/{collection_id}/video/{video_id}")
def add_to_collection(collection_id: str, video_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        if not c.execute("SELECT 1 FROM save_collections WHERE id=? AND user_id=?", (collection_id, uid)).fetchone():
            raise HTTPException(404, "Collection not found")
        if not c.execute("SELECT 1 FROM videos WHERE id=? AND status='ready'", (video_id,)).fetchone():
            raise HTTPException(404, "Video not found")
        c.execute("INSERT OR IGNORE INTO saved_videos(user_id,video_id) VALUES(?,?)", (uid, video_id))
        c.execute("INSERT OR IGNORE INTO collection_items(collection_id,video_id) VALUES(?,?)", (collection_id, video_id))
        c.execute("UPDATE save_collections SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (collection_id,))
    return {"added": True, "collection_id": collection_id, "video_id": video_id}


@router.delete("/collections/{collection_id}/video/{video_id}")
def remove_from_collection(collection_id: str, video_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        if not c.execute("SELECT 1 FROM save_collections WHERE id=? AND user_id=?", (collection_id, uid)).fetchone():
            raise HTTPException(404, "Collection not found")
        c.execute("DELETE FROM collection_items WHERE collection_id=? AND video_id=?", (collection_id, video_id))
        c.execute("UPDATE save_collections SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (collection_id,))
    return {"added": False, "collection_id": collection_id, "video_id": video_id}


@router.get("/collections/{collection_id}")
def collection_detail(collection_id: str, limit: int = 50, offset: int = 0, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    with db() as c:
        col = c.execute("SELECT * FROM save_collections WHERE id=? AND user_id=?", (collection_id, uid)).fetchone()
        if not col:
            raise HTTPException(404, "Collection not found")
        rows = c.execute("""
            SELECT v.*, u.username, u.display_name, 1 AS saved,
                   CASE WHEN l.user_id IS NULL THEN 0 ELSE 1 END AS liked
            FROM collection_items ci
            JOIN videos v ON v.id=ci.video_id
            JOIN users u ON u.id=v.user_id
            LEFT JOIN likes l ON l.video_id=v.id AND l.user_id=?
            WHERE ci.collection_id=? AND v.status='ready'
            ORDER BY ci.created_at DESC LIMIT ? OFFSET ?
        """, (uid, collection_id, limit, offset)).fetchall()
        total = c.execute("SELECT COUNT(*) FROM collection_items ci JOIN videos v ON v.id=ci.video_id WHERE ci.collection_id=? AND v.status='ready'", (collection_id,)).fetchone()[0]
    return {"collection": dict(col), "items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset, "has_more": offset + len(rows) < total}
