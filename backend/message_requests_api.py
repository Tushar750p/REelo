from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from main import current_user, db
from automated_moderation import moderate_text

router = APIRouter(prefix="/api/message-requests", tags=["message-requests"])

class RequestAction(BaseModel):
    action: str


def require_user(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_table(c):
    c.execute("""CREATE TABLE IF NOT EXISTS message_requests(
        id TEXT PRIMARY KEY,
        requester_id TEXT NOT NULL,
        recipient_id TEXT NOT NULL,
        body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(requester_id, recipient_id)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_message_requests_recipient_status ON message_requests(recipient_id,status,created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_message_requests_requester_status ON message_requests(requester_id,status,created_at)")


def blocked(c, a, b):
    c.execute("CREATE TABLE IF NOT EXISTS blocked_users(blocker_id TEXT NOT NULL, blocked_id TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(blocker_id,blocked_id))")
    return bool(c.execute("SELECT 1 FROM blocked_users WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)", (a,b,b,a)).fetchone())


def following(c, a, b):
    return bool(c.execute("SELECT 1 FROM follows WHERE follower_id=? AND following_id=?", (a,b)).fetchone())


def request_payload(r):
    return dict(r)


@router.get("")
def list_requests(kind: str = "inbox", limit: int = 50, offset: int = 0, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    kind = kind.strip().lower()
    if kind not in {"inbox", "sent"}:
        raise HTTPException(400, "kind must be inbox or sent")
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    with db() as c:
        ensure_table(c)
        if kind == "inbox":
            rows = c.execute("SELECT r.id,r.requester_id user_id,u.username,u.display_name,u.bio,r.body,r.status,r.created_at,r.updated_at FROM message_requests r JOIN users u ON u.id=r.requester_id WHERE r.recipient_id=? AND r.status='pending' ORDER BY r.created_at DESC LIMIT ? OFFSET ?", (uid,limit,offset)).fetchall()
            total = c.execute("SELECT COUNT(*) FROM message_requests WHERE recipient_id=? AND status='pending'", (uid,)).fetchone()[0]
        else:
            rows = c.execute("SELECT r.id,r.recipient_id user_id,u.username,u.display_name,u.bio,r.body,r.status,r.created_at,r.updated_at FROM message_requests r JOIN users u ON u.id=r.recipient_id WHERE r.requester_id=? AND r.status='pending' ORDER BY r.created_at DESC LIMIT ? OFFSET ?", (uid,limit,offset)).fetchall()
            total = c.execute("SELECT COUNT(*) FROM message_requests WHERE requester_id=? AND status='pending'", (uid,)).fetchone()[0]
    return {"items":[request_payload(r) for r in rows],"kind":kind,"total":total,"limit":limit,"offset":offset,"has_more":offset+len(rows)<total,"version":"1.0"}


@router.get("/summary")
def request_summary(authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        incoming = c.execute("SELECT COUNT(*) FROM message_requests WHERE recipient_id=? AND status='pending'", (uid,)).fetchone()[0]
        outgoing = c.execute("SELECT COUNT(*) FROM message_requests WHERE requester_id=? AND status='pending'", (uid,)).fetchone()[0]
    return {"incoming": incoming, "outgoing": outgoing, "total": incoming, "version":"1.0"}


@router.post("")
def create_request(user_id: str, body: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization); body = body.strip()
    if uid == user_id: raise HTTPException(400, "Cannot message yourself")
    if not body or len(body) > 2000: raise HTTPException(400, "Message must be 1-2000 characters")
    safety = moderate_text(body)
    if safety.action in {"review", "limit"}: raise HTTPException(400, "Message blocked by safety filters")
    with db() as c:
        ensure_table(c)
        if not c.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone(): raise HTTPException(404, "User not found")
        if blocked(c, uid, user_id): raise HTTPException(403, "Messaging is unavailable because one of the users is blocked")
        existing = c.execute("SELECT id,status FROM message_requests WHERE requester_id=? AND recipient_id=?", (uid,user_id)).fetchone()
        if existing and existing["status"] == "pending":
            raise HTTPException(409, "Message request already pending")
        if existing:
            c.execute("UPDATE message_requests SET body=?,status='pending',updated_at=CURRENT_TIMESTAMP WHERE id=?", (body,existing["id"]))
            rid = existing["id"]
        else:
            rid = uuid4().hex
            c.execute("INSERT INTO message_requests(id,requester_id,recipient_id,body) VALUES(?,?,?,?)", (rid,uid,user_id,body))
        r = c.execute("SELECT r.id,r.requester_id user_id,u.username,u.display_name,r.body,r.status,r.created_at,r.updated_at FROM message_requests r JOIN users u ON u.id=r.requester_id WHERE r.id=?", (rid,)).fetchone()
    return {"request": dict(r), "status":"pending", "version":"1.0"}


@router.post("/{request_id}/accept")
def accept_request(request_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        r = c.execute("SELECT * FROM message_requests WHERE id=? AND recipient_id=? AND status='pending'", (request_id,uid)).fetchone()
        if not r: raise HTTPException(404, "Message request not found")
        if blocked(c, uid, r["requester_id"]): raise HTTPException(403, "Messaging is unavailable because one of the users is blocked")
        c.execute("CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS conversation_members(conversation_id TEXT NOT NULL,user_id TEXT NOT NULL,PRIMARY KEY(conversation_id,user_id))")
        c.execute("CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,sender_id TEXT NOT NULL,body TEXT NOT NULL,read_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        existing = c.execute("SELECT a.conversation_id FROM conversation_members a JOIN conversation_members b ON b.conversation_id=a.conversation_id WHERE a.user_id=? AND b.user_id=? LIMIT 1", (uid,r["requester_id"])).fetchone()
        cid = existing[0] if existing else uuid4().hex
        if not existing:
            c.execute("INSERT INTO conversations(id) VALUES(?)", (cid,))
            c.execute("INSERT INTO conversation_members(conversation_id,user_id) VALUES(?,?),(?,?)", (cid,uid,cid,r["requester_id"]))
        mid = uuid4().hex
        c.execute("INSERT INTO messages(id,conversation_id,sender_id,body,delivered_at) VALUES(?,?,?, ?,CURRENT_TIMESTAMP)", (mid,cid,r["requester_id"],r["body"]))
        c.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))
        c.execute("UPDATE message_requests SET status='accepted',updated_at=CURRENT_TIMESTAMP WHERE id=?", (request_id,))
    return {"ok":True,"status":"accepted","conversation_id":cid,"request_id":request_id,"message_id":mid}


@router.post("/{request_id}/decline")
def decline_request(request_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        cur = c.execute("UPDATE message_requests SET status='declined',updated_at=CURRENT_TIMESTAMP WHERE id=? AND recipient_id=? AND status='pending'", (request_id,uid))
        if not cur.rowcount: raise HTTPException(404, "Message request not found")
    return {"ok":True,"status":"declined","request_id":request_id}


@router.delete("/{request_id}")
def delete_request(request_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        cur = c.execute("UPDATE message_requests SET status='declined',updated_at=CURRENT_TIMESTAMP WHERE id=? AND ((recipient_id=? AND status='pending') OR (requester_id=? AND status='pending'))", (request_id,uid,uid))
        if not cur.rowcount: raise HTTPException(404, "Message request not found")
    return {"ok":True,"status":"deleted","request_id":request_id}


@router.post("/{request_id}/block")
def block_request(request_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        r = c.execute("SELECT requester_id FROM message_requests WHERE id=? AND recipient_id=? AND status='pending'", (request_id,uid)).fetchone()
        if not r: raise HTTPException(404, "Message request not found")
        c.execute("CREATE TABLE IF NOT EXISTS blocked_users(blocker_id TEXT NOT NULL, blocked_id TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(blocker_id,blocked_id))")
        c.execute("INSERT OR IGNORE INTO blocked_users(blocker_id,blocked_id) VALUES(?,?)", (uid,r["requester_id"]))
        c.execute("UPDATE message_requests SET status='blocked',updated_at=CURRENT_TIMESTAMP WHERE id=?", (request_id,))
    return {"ok":True,"status":"blocked","request_id":request_id,"user_id":r["requester_id"]}
