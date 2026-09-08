from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4

from main import current_user, db

router = APIRouter(prefix="/api/messages", tags=["messaging-v2"])


def require_user(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_column(c, table, column, definition):
    cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS conversation_members(conversation_id TEXT NOT NULL,user_id TEXT NOT NULL,PRIMARY KEY(conversation_id,user_id))")
    c.execute("CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,sender_id TEXT NOT NULL,body TEXT NOT NULL,read_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    ensure_column(c, "messages", "delivered_at", "TEXT")
    ensure_column(c, "conversation_members", "muted", "INTEGER DEFAULT 0")
    ensure_column(c, "conversation_members", "archived", "INTEGER DEFAULT 0")
    ensure_column(c, "conversation_members", "pinned", "INTEGER DEFAULT 0")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id,created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_sender_read ON messages(conversation_id,sender_id,read_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_members_user ON conversation_members(user_id,conversation_id)")


class MessageIn(BaseModel):
    body: str


class ConversationUpdate(BaseModel):
    muted: bool | None = None
    archived: bool | None = None
    pinned: bool | None = None


def conversation_for(c, uid, other_id):
    row = c.execute("""
        SELECT a.conversation_id FROM conversation_members a
        JOIN conversation_members b ON b.conversation_id=a.conversation_id
        WHERE a.user_id=? AND b.user_id=? LIMIT 1
    """, (uid, other_id)).fetchone()
    return row[0] if row else None


@router.get("")
def conversations(limit: int = 50, offset: int = 0, include_archived: bool = False, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    with db() as c:
        ensure_tables(c)
        archived_filter = "" if include_archived else " AND COALESCE(cm.archived,0)=0"
        rows = c.execute(f"""
            SELECT cm.conversation_id,
                   other.user_id,u.username,u.display_name,
                   m.body last_message,m.created_at last_message_at,
                   COALESCE((SELECT COUNT(*) FROM messages um WHERE um.conversation_id=cm.conversation_id AND um.sender_id<>? AND um.read_at IS NULL),0) unread_count,
                   COALESCE(cm.muted,0) muted,COALESCE(cm.archived,0) archived,COALESCE(cm.pinned,0) pinned,
                   COALESCE(m.delivered_at,m.created_at) last_message_delivered_at,
                   m.read_at last_message_read_at
            FROM conversation_members cm
            JOIN conversation_members other ON other.conversation_id=cm.conversation_id AND other.user_id<>cm.user_id
            JOIN users u ON u.id=other.user_id
            LEFT JOIN messages m ON m.id=(SELECT id FROM messages lm WHERE lm.conversation_id=cm.conversation_id ORDER BY lm.created_at DESC LIMIT 1)
            WHERE cm.user_id=? {archived_filter}
            ORDER BY COALESCE(cm.pinned,0) DESC, COALESCE(m.created_at,'') DESC
            LIMIT ? OFFSET ?
        """, (uid, uid, limit, offset)).fetchall()
        total = c.execute(f"SELECT COUNT(*) FROM conversation_members cm WHERE cm.user_id=? {archived_filter}", (uid,)).fetchone()[0]
        unread = c.execute("""SELECT COUNT(*) FROM messages m JOIN conversation_members cm ON cm.conversation_id=m.conversation_id AND cm.user_id=? WHERE m.sender_id<>? AND m.read_at IS NULL AND COALESCE(cm.archived,0)=0""", (uid, uid)).fetchone()[0]
    return {"items":[dict(r) for r in rows], "limit":limit, "offset":offset, "has_more":offset+len(rows)<total, "total":total, "unread_count":unread, "version":"2.0"}


@router.post("/{user_id}")
def send_message(user_id: str, data: MessageIn, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    body = data.body.strip()
    if uid == user_id: raise HTTPException(400, "Cannot message yourself")
    if not body or len(body) > 2000: raise HTTPException(400, "Message must be 1-2000 characters")
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone(): raise HTTPException(404, "User not found")
        cid = conversation_for(c, uid, user_id)
        if not cid:
            cid = uuid4().hex
            c.execute("INSERT INTO conversations(id) VALUES(?)", (cid,))
            c.execute("INSERT INTO conversation_members(conversation_id,user_id) VALUES(?,?),(?,?)", (cid,uid,cid,user_id))
        mid = uuid4().hex
        c.execute("INSERT INTO messages(id,conversation_id,sender_id,body,delivered_at) VALUES(?,?,?, ?,CURRENT_TIMESTAMP)", (mid,cid,uid,body))
        c.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))
        row = c.execute("SELECT m.id,m.body,m.sender_id,m.created_at,m.delivered_at,m.read_at,u.username,u.display_name FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.id=?", (mid,)).fetchone()
    return {"conversation_id":cid,"message":dict(row),"status":"sent"}


@router.get("/{conversation_id}/messages")
def message_list(conversation_id: str, limit: int = 50, before: str | None = None, authorization: str | None = Header(default=None)):
    uid = require_user(authorization); limit=max(1,min(limit,100))
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT 1 FROM conversation_members WHERE conversation_id=? AND user_id=?", (conversation_id,uid)).fetchone(): raise HTTPException(403,"Conversation not found")
        params=[conversation_id]; where="m.conversation_id=?"
        if before: where += " AND m.created_at < ?"; params.append(before)
        params.append(limit)
        rows=c.execute(f"SELECT m.id,m.body,m.sender_id,m.created_at,m.delivered_at,m.read_at,u.username,u.display_name FROM messages m JOIN users u ON u.id=m.sender_id WHERE {where} ORDER BY m.created_at DESC LIMIT ?",params).fetchall()
        unread_ids = [r[0] for r in c.execute("SELECT id FROM messages WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",(conversation_id,uid)).fetchall()]
        if unread_ids:
            c.execute("UPDATE messages SET read_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",(conversation_id,uid))
    return {"items":[dict(r) for r in reversed(rows)],"limit":limit,"before":before,"has_more":len(rows)==limit,"marked_read":len(unread_ids)}


@router.post("/{conversation_id}/read")
def mark_read(conversation_id: str, authorization: str | None = Header(default=None)):
    uid=require_user(authorization)
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT 1 FROM conversation_members WHERE conversation_id=? AND user_id=?",(conversation_id,uid)).fetchone(): raise HTTPException(403,"Conversation not found")
        cur=c.execute("UPDATE messages SET read_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",(conversation_id,uid))
    return {"ok":True,"read_count":cur.rowcount}


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: str, data: ConversationUpdate, authorization: str | None = Header(default=None)):
    uid=require_user(authorization)
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT 1 FROM conversation_members WHERE conversation_id=? AND user_id=?",(conversation_id,uid)).fetchone(): raise HTTPException(403,"Conversation not found")
        fields=[]; values=[]
        for name,value in (("muted",data.muted),("archived",data.archived),("pinned",data.pinned)):
            if value is not None: fields.append(f"{name}=?"); values.append(int(value))
        if fields:
            values += [conversation_id,uid]
            c.execute(f"UPDATE conversation_members SET {','.join(fields)} WHERE conversation_id=? AND user_id=?",values)
        row=c.execute("SELECT muted,archived,pinned FROM conversation_members WHERE conversation_id=? AND user_id=?",(conversation_id,uid)).fetchone()
    return {"conversation_id":conversation_id,"settings":dict(row)}


@router.get("/unread/summary")
def unread_summary(authorization: str | None = Header(default=None)):
    uid=require_user(authorization)
    with db() as c:
        ensure_tables(c)
        row=c.execute("""SELECT COUNT(*) total_unread,COUNT(DISTINCT m.conversation_id) conversations_with_unread FROM messages m JOIN conversation_members cm ON cm.conversation_id=m.conversation_id AND cm.user_id=? WHERE m.sender_id<>? AND m.read_at IS NULL AND COALESCE(cm.archived,0)=0""",(uid,uid)).fetchone()
    return dict(row)
