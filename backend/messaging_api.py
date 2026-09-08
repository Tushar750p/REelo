from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone
from threading import Lock
from main import current_user, db
from automated_moderation import moderate_text

router = APIRouter(prefix="/api/messages", tags=["messaging-v2"])
_typing = {}
_typing_lock = Lock()

def require_user(authorization):
    uid = current_user(authorization)
    if not uid: raise HTTPException(401, "Login required")
    return uid

def ensure_column(c, table, column, definition):
    cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols: c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS conversation_members(conversation_id TEXT NOT NULL,user_id TEXT NOT NULL,PRIMARY KEY(conversation_id,user_id))")
    c.execute("CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,sender_id TEXT NOT NULL,body TEXT NOT NULL,read_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS message_reactions(message_id TEXT NOT NULL,user_id TEXT NOT NULL,reaction TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(message_id,user_id))")
    ensure_column(c,"messages","delivered_at","TEXT"); ensure_column(c,"conversation_members","muted","INTEGER DEFAULT 0"); ensure_column(c,"conversation_members","archived","INTEGER DEFAULT 0"); ensure_column(c,"conversation_members","pinned","INTEGER DEFAULT 0")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id,created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_sender_read ON messages(conversation_id,sender_id,read_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_members_user ON conversation_members(user_id,conversation_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reactions_message ON message_reactions(message_id)")

class MessageIn(BaseModel): body: str
class ConversationUpdate(BaseModel):
    muted: bool | None = None; archived: bool | None = None; pinned: bool | None = None
class ReactionIn(BaseModel): reaction: str
class TypingIn(BaseModel): typing: bool = True

def conversation_for(c,uid,other_id):
    row=c.execute("SELECT a.conversation_id FROM conversation_members a JOIN conversation_members b ON b.conversation_id=a.conversation_id WHERE a.user_id=? AND b.user_id=? LIMIT 1",(uid,other_id)).fetchone()
    return row[0] if row else None

def assert_member(c,cid,uid):
    if not c.execute("SELECT 1 FROM conversation_members WHERE conversation_id=? AND user_id=?",(cid,uid)).fetchone(): raise HTTPException(403,"Conversation not found")

def message_payload(c,mid,uid):
    row=c.execute("SELECT m.id,m.body,m.sender_id,m.created_at,m.delivered_at,m.read_at,u.username,u.display_name FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.id=?",(mid,)).fetchone()
    if not row: raise HTTPException(404,"Message not found")
    reactions=c.execute("SELECT reaction,COUNT(*) count FROM message_reactions WHERE message_id=? GROUP BY reaction ORDER BY count DESC",(mid,)).fetchall()
    mine=c.execute("SELECT reaction FROM message_reactions WHERE message_id=? AND user_id=?",(mid,uid)).fetchone()
    out=dict(row); out["reactions"]=[dict(r) for r in reactions]; out["my_reaction"]=mine[0] if mine else None
    return out

@router.get("")
def conversations(limit:int=50,offset:int=0,include_archived:bool=False,authorization:str|None=Header(default=None)):
    uid=require_user(authorization); limit=max(1,min(limit,100)); offset=max(0,offset)
    with db() as c:
        ensure_tables(c); af="" if include_archived else " AND COALESCE(cm.archived,0)=0"
        rows=c.execute(f"SELECT cm.conversation_id,other.user_id,u.username,u.display_name,m.body last_message,m.created_at last_message_at,COALESCE((SELECT COUNT(*) FROM messages um WHERE um.conversation_id=cm.conversation_id AND um.sender_id<>? AND um.read_at IS NULL),0) unread_count,COALESCE(cm.muted,0) muted,COALESCE(cm.archived,0) archived,COALESCE(cm.pinned,0) pinned,COALESCE(m.delivered_at,m.created_at) last_message_delivered_at,m.read_at last_message_read_at FROM conversation_members cm JOIN conversation_members other ON other.conversation_id=cm.conversation_id AND other.user_id<>cm.user_id JOIN users u ON u.id=other.user_id LEFT JOIN messages m ON m.id=(SELECT id FROM messages lm WHERE lm.conversation_id=cm.conversation_id ORDER BY lm.created_at DESC LIMIT 1) WHERE cm.user_id=? {af} ORDER BY COALESCE(cm.pinned,0) DESC,COALESCE(m.created_at,'') DESC LIMIT ? OFFSET ?",(uid,uid,limit,offset)).fetchall()
        total=c.execute(f"SELECT COUNT(*) FROM conversation_members cm WHERE cm.user_id=? {af}",(uid,)).fetchone()[0]
        unread=c.execute("SELECT COUNT(*) FROM messages m JOIN conversation_members cm ON cm.conversation_id=m.conversation_id AND cm.user_id=? WHERE m.sender_id<>? AND m.read_at IS NULL AND COALESCE(cm.archived,0)=0",(uid,uid)).fetchone()[0]
    return {"items":[dict(r) for r in rows],"limit":limit,"offset":offset,"has_more":offset+len(rows)<total,"total":total,"unread_count":unread,"version":"2.1"}

@router.post("/{user_id}")
def send_message(user_id:str,data:MessageIn,authorization:str|None=Header(default=None)):
    uid=require_user(authorization); body=data.body.strip()
    if uid==user_id: raise HTTPException(400,"Cannot message yourself")
    if not body or len(body)>2000: raise HTTPException(400,"Message must be 1-2000 characters")
    safety=moderate_text(body)
    if safety.action=="review": raise HTTPException(400,"Message blocked by safety filters")
    if safety.action=="limit": raise HTTPException(400,"Message contains content that cannot be sent")
    with db() as c:
        ensure_tables(c)
        if not c.execute("SELECT 1 FROM users WHERE id=?",(user_id,)).fetchone(): raise HTTPException(404,"User not found")
        cid=conversation_for(c,uid,user_id)
        if not cid:
            cid=uuid4().hex; c.execute("INSERT INTO conversations(id) VALUES(?)",(cid)); c.execute("INSERT INTO conversation_members(conversation_id,user_id) VALUES(?,?),(?,?)",(cid,uid,cid,user_id))
        mid=uuid4().hex; c.execute("INSERT INTO messages(id,conversation_id,sender_id,body,delivered_at) VALUES(?,?,?, ?,CURRENT_TIMESTAMP)",(mid,cid,uid,body)); c.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(cid,))
        row=message_payload(c,mid,uid)
    return {"conversation_id":cid,"message":row,"status":"sent"}

@router.get("/{conversation_id}/messages")
def message_list(conversation_id:str,limit:int=50,before:str|None=None,authorization:str|None=Header(default=None)):
    uid=require_user(authorization); limit=max(1,min(limit,100))
    with db() as c:
        ensure_tables(c); assert_member(c,conversation_id,uid); params=[conversation_id]; where="m.conversation_id=?"
        if before: where+=" AND m.created_at < ?"; params.append(before)
        params.append(limit); rows=c.execute(f"SELECT m.id,m.body,m.sender_id,m.created_at,m.delivered_at,m.read_at,u.username,u.display_name FROM messages m JOIN users u ON u.id=m.sender_id WHERE {where} ORDER BY m.created_at DESC LIMIT ?",params).fetchall(); ids=[r[0] for r in rows]
        grouped={}; my={}
        if ids:
            ph=','.join('?' for _ in ids); rx=c.execute(f"SELECT message_id,reaction,COUNT(*) count FROM message_reactions WHERE message_id IN ({ph}) GROUP BY message_id,reaction",ids).fetchall(); mine=c.execute(f"SELECT message_id,reaction FROM message_reactions WHERE user_id=? AND message_id IN ({ph})",[uid,*ids]).fetchall()
            for r in rx: grouped.setdefault(r[0],[]).append({"reaction":r[1],"count":r[2]})
            my={r[0]:r[1] for r in mine}
        unread_ids=[r[0] for r in c.execute("SELECT id FROM messages WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",(conversation_id,uid)).fetchall()]
        if unread_ids: c.execute("UPDATE messages SET read_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",(conversation_id,uid))
    items=[]
    for r in reversed(rows): x=dict(r); x["reactions"]=grouped.get(r[0],[]); x["my_reaction"]=my.get(r[0]); items.append(x)
    return {"items":items,"limit":limit,"before":before,"has_more":len(rows)==limit,"marked_read":len(unread_ids),"version":"2.1"}

@router.post("/{conversation_id}/read")
def mark_read(conversation_id:str,authorization:str|None=Header(default=None)):
    uid=require_user(authorization)
    with db() as c: ensure_tables(c); assert_member(c,conversation_id,uid); cur=c.execute("UPDATE messages SET read_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",(conversation_id,uid))
    return {"ok":True,"read_count":cur.rowcount}

@router.post("/{conversation_id}/typing")
def set_typing(conversation_id:str,data:TypingIn,authorization:str|None=Header(default=None)):
    uid=require_user(authorization)
    with db() as c: ensure_tables(c); assert_member(c,conversation_id,uid)
    with _typing_lock:
        if data.typing: _typing[(conversation_id,uid)]=datetime.now(timezone.utc).timestamp()
        else: _typing.pop((conversation_id,uid),None)
    return {"ok":True,"typing":data.typing}

@router.get("/{conversation_id}/typing")
def get_typing(conversation_id:str,authorization:str|None=Header(default=None)):
    uid=require_user(authorization)
    with db() as c: ensure_tables(c); assert_member(c,conversation_id,uid); members=[r[0] for r in c.execute("SELECT user_id FROM conversation_members WHERE conversation_id=? AND user_id<>?",(conversation_id,uid)).fetchall()]
    now=datetime.now(timezone.utc).timestamp()
    with _typing_lock:
        active=[m for m in members if now-_typing.get((conversation_id,m),0)<4]
        for key,ts in list(_typing.items()):
            if now-ts>=4: _typing.pop(key,None)
    return {"typing":bool(active),"user_ids":active}

@router.put("/message/{message_id}/reaction")
def react(message_id:str,data:ReactionIn,authorization:str|None=Header(default=None)):
    uid=require_user(authorization); reaction=data.reaction.strip(); allowed={"❤️","😂","🔥","👍","😮","😢","👏"}
    if reaction not in allowed: raise HTTPException(400,"Unsupported reaction")
    with db() as c:
        ensure_tables(c); row=c.execute("SELECT conversation_id FROM messages WHERE id=?",(message_id,)).fetchone()
        if not row: raise HTTPException(404,"Message not found")
        assert_member(c,row[0],uid); c.execute("INSERT INTO message_reactions(message_id,user_id,reaction) VALUES(?,?,?) ON CONFLICT(message_id,user_id) DO UPDATE SET reaction=excluded.reaction,created_at=CURRENT_TIMESTAMP",(message_id,uid,reaction)); payload=message_payload(c,message_id,uid)
    return {"ok":True,"message":payload}

@router.delete("/message/{message_id}/reaction")
def remove_reaction(message_id:str,authorization:str|None=Header(default=None)):
    uid=require_user(authorization)
    with db() as c:
        ensure_tables(c); row=c.execute("SELECT conversation_id FROM messages WHERE id=?",(message_id,)).fetchone()
        if not row: raise HTTPException(404,"Message not found")
        assert_member(c,row[0],uid); c.execute("DELETE FROM message_reactions WHERE message_id=? AND user_id=?",(message_id,uid)); payload=message_payload(c,message_id,uid)
    return {"ok":True,"message":payload}

@router.patch("/{conversation_id}")
def update_conversation(conversation_id:str,data:ConversationUpdate,authorization:str|None=Header(default=None)):
    uid=require_user(authorization)
    with db() as c:
        ensure_tables(c); assert_member(c,conversation_id,uid); fields=[]; values=[]
        for name,value in (("muted",data.muted),("archived",data.archived),("pinned",data.pinned)):
            if value is not None: fields.append(f"{name}=?"); values.append(int(value))
        if fields: values += [conversation_id,uid]; c.execute(f"UPDATE conversation_members SET {','.join(fields)} WHERE conversation_id=? AND user_id=?",values)
        row=c.execute("SELECT muted,archived,pinned FROM conversation_members WHERE conversation_id=? AND user_id=?",(conversation_id,uid)).fetchone()
    return {"conversation_id":conversation_id,"settings":dict(row)}

@router.get("/unread/summary")
def unread_summary(authorization:str|None=Header(default=None)):
    uid=require_user(authorization)
    with db() as c: ensure_tables(c); row=c.execute("SELECT COUNT(*) total_unread,COUNT(DISTINCT m.conversation_id) conversations_with_unread FROM messages m JOIN conversation_members cm ON cm.conversation_id=m.conversation_id AND cm.user_id=? WHERE m.sender_id<>? AND m.read_at IS NULL AND COALESCE(cm.archived,0)=0",(uid,uid)).fetchone()
    return dict(row)
