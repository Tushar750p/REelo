from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4

from main import current_user, db

router = APIRouter(prefix="/api/messages", tags=["messaging"])


def require_user(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS conversation_members(conversation_id TEXT NOT NULL,user_id TEXT NOT NULL,PRIMARY KEY(conversation_id,user_id))")
    c.execute("CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,sender_id TEXT NOT NULL,body TEXT NOT NULL,read_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id,created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_members_user ON conversation_members(user_id,conversation_id)")


class MessageIn(BaseModel):
    body: str


@router.get("")
def conversations(authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_tables(c)
        rows = c.execute("""
            SELECT cm.conversation_id,
                   u.id user_id,u.username,u.display_name,
                   m.body last_message,m.created_at last_message_at,
                   COALESCE((SELECT COUNT(*) FROM messages um WHERE um.conversation_id=cm.conversation_id AND um.sender_id<>? AND um.read_at IS NULL),0) unread
            FROM conversation_members cm
            JOIN conversation_members other ON other.conversation_id=cm.conversation_id AND other.user_id<>cm.user_id
            JOIN users u ON u.id=other.user_id
            LEFT JOIN messages m ON m.id=(SELECT id FROM messages lm WHERE lm.conversation_id=cm.conversation_id ORDER BY lm.created_at DESC LIMIT 1)
            WHERE cm.user_id=?
            ORDER BY COALESCE(m.created_at,'') DESC
        """, (uid, uid)).fetchall()
    return {"items":[dict(r) for r in rows]}


@router.post("/{user_id}")
def send_message(user_id: str, data: MessageIn, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    body = data.body.strip()
    if uid == user_id:
        raise HTTPException(400, "Cannot message yourself")
    if not body or len(body) > 2000:
        raise HTTPException(400, "Message must be 1-2000 characters")
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
            raise HTTPException(404, "User not found")
        existing = c.execute("""
            SELECT a.conversation_id FROM conversation_members a
            JOIN conversation_members b ON b.conversation_id=a.conversation_id
            WHERE a.user_id=? AND b.user_id=? LIMIT 1
        """, (uid, user_id)).fetchone()
        cid = existing[0] if existing else uuid4().hex
        if not existing:
            c.execute("INSERT INTO conversations(id) VALUES(?)", (cid,))
            c.execute("INSERT INTO conversation_members(conversation_id,user_id) VALUES(?,?),(?,?)", (cid,uid,cid,user_id))
        mid = uuid4().hex
        c.execute("INSERT INTO messages(id,conversation_id,sender_id,body) VALUES(?,?,?,?)", (mid,cid,uid,body))
        c.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))
        row = c.execute("SELECT m.id,m.body,m.sender_id,m.created_at,u.username,u.display_name FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.id=?", (mid,)).fetchone()
    return {"conversation_id":cid,"message":dict(row)}


@router.get("/{conversation_id}/messages")
def message_list(conversation_id: str, limit: int = 50, before: str | None = None, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    limit = max(1, min(limit, 100))
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT 1 FROM conversation_members WHERE conversation_id=? AND user_id=?", (conversation_id,uid)).fetchone():
            raise HTTPException(403, "Conversation not found")
        params=[conversation_id,limit]
        where="m.conversation_id=?"
        if before:
            where += " AND m.created_at < ?"
            params=[conversation_id,before,limit]
        rows=c.execute(f"SELECT m.id,m.body,m.sender_id,m.created_at,m.read_at,u.username,u.display_name FROM messages m JOIN users u ON u.id=m.sender_id WHERE {where} ORDER BY m.created_at DESC LIMIT ?",params).fetchall()
        c.execute("UPDATE messages SET read_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",(conversation_id,uid))
    return {"items":[dict(r) for r in reversed(rows)],"limit":limit,"before":before}


@router.post("/{conversation_id}/read")
def mark_read(conversation_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT 1 FROM conversation_members WHERE conversation_id=? AND user_id=?", (conversation_id,uid)).fetchone():
            raise HTTPException(403, "Conversation not found")
        c.execute("UPDATE messages SET read_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",(conversation_id,uid))
    return {"ok":True}
