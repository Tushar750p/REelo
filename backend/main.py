from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from uuid import uuid4
import hashlib
import hmac
import os
import secrets
import sqlite3

ROOT = Path(__file__).parent
MEDIA = ROOT / "media"
MEDIA.mkdir(exist_ok=True)
DB = ROOT / "reelo.db"
SECRET = os.getenv("REELO_SECRET", "change-this-in-production").encode()

app = FastAPI(title="REelo API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=MEDIA), name="media")

def db():
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row; return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, display_name TEXT NOT NULL, bio TEXT DEFAULT '', followers INTEGER DEFAULT 0, following INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT NOT NULL, caption TEXT DEFAULT '', likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, views INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS likes(user_id TEXT, video_id TEXT, PRIMARY KEY(user_id, video_id));
        CREATE TABLE IF NOT EXISTS follows(follower_id TEXT, following_id TEXT, PRIMARY KEY(follower_id, following_id));
        CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY, user_id TEXT, video_id TEXT, body TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, user_id TEXT, video_id TEXT, action TEXT, seconds REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            uid="demo-user"; c.execute("INSERT INTO users(id,username,password_hash,display_name,bio) VALUES(?,?,?,?,?)",(uid,"reelo_creator",hash_password("demo"),"REelo Creator","Create. Watch. Connect."))
        if not c.execute("SELECT 1 FROM videos LIMIT 1").fetchone():
            uid=c.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
            c.execute("INSERT INTO videos(id,user_id,filename,caption,likes,comments,views) VALUES(?,?,?,?,?,?,?)",("demo-1",uid,"https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4","Build your vibe. Share your story. 🚀",12400,321,85000))
            c.execute("INSERT INTO videos(id,user_id,filename,caption,likes,comments,views) VALUES(?,?,?,?,?,?,?)",("demo-2",uid,"https://www.w3schools.com/html/mov_bbb.mp4","Create something people remember.",8700,142,54000))

def hash_password(password: str) -> str:
    salt=secrets.token_bytes(16); digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,120_000); return salt.hex()+":"+digest.hex()

def verify_password(password: str, stored: str) -> bool:
    salt,digest=stored.split(":",1); check=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),120_000).hex(); return hmac.compare_digest(check,digest)

def token_for(user_id: str) -> str:
    payload=user_id.encode().hex(); sig=hmac.new(SECRET,payload.encode(),hashlib.sha256).hexdigest(); return payload+"."+sig

def current_user(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "): return None
    raw=authorization.split(" ",1)[1]
    try:
        payload,sig=raw.split(".",1); expected=hmac.new(SECRET,payload.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected): return None
        return bytes.fromhex(payload).decode()
    except (ValueError,UnicodeDecodeError): return None

def public_user(row):
    return {"id":row["id"],"username":row["username"],"display_name":row["display_name"],"bio":row["bio"],"followers":row["followers"],"following":row["following"]}

class Credentials(BaseModel):
    username: str
    password: str
    display_name: str | None = None

class ProfileUpdate(BaseModel):
    display_name: str | None = None
    bio: str | None = None

class CommentIn(BaseModel):
    body: str

@app.on_event("startup")
def startup(): init_db()

@app.get("/health")
def health(): return {"status":"ok","service":"reelo-api","version":app.version}

@app.post("/api/auth/register")
def register(data: Credentials):
    username=data.username.strip().lower()
    if len(username)<3 or len(data.password)<6: raise HTTPException(400,"Username must be 3+ chars and password 6+ chars")
    uid=uuid4().hex
    try:
        with db() as c: c.execute("INSERT INTO users(id,username,password_hash,display_name) VALUES(?,?,?,?)",(uid,username,hash_password(data.password),data.display_name.strip() if data.display_name else username))
    except sqlite3.IntegrityError: raise HTTPException(409,"Username already exists")
    with db() as c: row=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    return {"token":token_for(uid),"user":public_user(row)}

@app.post("/api/auth/login")
def login(data: Credentials):
    with db() as c: row=c.execute("SELECT * FROM users WHERE username=?",(data.username.strip().lower(),)).fetchone()
    if not row or not verify_password(data.password,row["password_hash"]): raise HTTPException(401,"Invalid username or password")
    return {"token":token_for(row["id"]),"user":public_user(row)}

@app.get("/api/me")
def me(authorization: str | None=Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,"Login required")
    with db() as c: row=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    if not row: raise HTTPException(401,"Session is invalid")
    return {"user":public_user(row)}

@app.patch("/api/me")
def update_me(data: ProfileUpdate, authorization: str | None=Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,"Login required")
    display=(data.display_name or "").strip(); bio=(data.bio or "").strip()
    if len(display)>80: raise HTTPException(400,"Display name must be 80 characters or less")
    if len(bio)>160: raise HTTPException(400,"Bio must be 160 characters or less")
    with db() as c:
        row=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        if not row: raise HTTPException(404,"User not found")
        c.execute("UPDATE users SET display_name=?, bio=? WHERE id=?",(display or row["display_name"],bio,uid))
        row=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    return {"user":public_user(row)}

@app.get("/api/feed")
def feed(limit:int=20,authorization:str|None=Header(default=None)):
    user_id=current_user(authorization); limit=max(1,min(limit,50))
    with db() as c:
        rows=c.execute("SELECT v.*,u.username,u.display_name,CASE WHEN ? IS NOT NULL AND EXISTS(SELECT 1 FROM likes l WHERE l.video_id=v.id AND l.user_id=?) THEN 1 ELSE 0 END liked FROM videos v JOIN users u ON u.id=v.user_id ORDER BY v.created_at DESC LIMIT ?",(user_id,user_id,limit)).fetchall()
    return {"items":[dict(r) for r in rows],"algorithm":"hybrid-v1"}

@app.get("/api/search")
def search(q:str):
    q=q.strip()
    with db() as c: rows=c.execute("SELECT v.*,u.username,u.display_name FROM videos v JOIN users u ON u.id=v.user_id WHERE v.caption LIKE ? OR u.username LIKE ? ORDER BY v.created_at DESC LIMIT 50",(f"%{q}%",f"%{q}%")).fetchall()
    return {"query":q,"items":[dict(r) for r in rows]}

@app.post("/api/videos/upload")
async def upload_video(file:UploadFile=File(...),caption:str=Form(""),authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,"Login required")
    if not (file.content_type or "").startswith("video/"): raise HTTPException(415,"Video file required")
    ext=Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if ext not in {".mp4",".mov",".webm",".m4v"}: raise HTTPException(415,"Unsupported video format")
    name=f"{uuid4().hex}{ext}"; dest=MEDIA/name
    with dest.open("wb") as out:
        while chunk:=await file.read(1024*1024): out.write(chunk)
    vid=uuid4().hex
    with db() as c: c.execute("INSERT INTO videos(id,user_id,filename,caption) VALUES(?,?,?,?)",(vid,uid,name,caption[:2200]))
    return {"id":vid,"status":"uploaded","url":f"/media/{name}"}

@app.post("/api/videos/{video_id}/like")
def like(video_id:str,authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,"Login required")
    with db() as c:
        if not c.execute("SELECT 1 FROM videos WHERE id=?",(video_id,)).fetchone(): raise HTTPException(404,"Video not found")
        exists=c.execute("SELECT 1 FROM likes WHERE user_id=? AND video_id=?",(uid,video_id)).fetchone()
        if exists: c.execute("DELETE FROM likes WHERE user_id=? AND video_id=?",(uid,video_id)); c.execute("UPDATE videos SET likes=MAX(likes-1,0) WHERE id=?",(video_id,)); liked=False
        else: c.execute("INSERT INTO likes(user_id,video_id) VALUES(?,?)",(uid,video_id)); c.execute("UPDATE videos SET likes=likes+1 WHERE id=?",(video_id,)); liked=True
        count=c.execute("SELECT likes FROM videos WHERE id=?",(video_id,)).fetchone()[0]
    return {"liked":liked,"likes":count}

@app.post("/api/videos/{video_id}/comments")
def comment(video_id:str,data:CommentIn,authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,"Login required")
    body=data.body.strip()
    if not body or len(body)>500: raise HTTPException(400,"Comment must be 1-500 characters")
    with db() as c:
        if not c.execute("SELECT 1 FROM videos WHERE id=?",(video_id,)).fetchone(): raise HTTPException(404,"Video not found")
        cid=uuid4().hex; c.execute("INSERT INTO comments(id,user_id,video_id,body) VALUES(?,?,?,?)",(cid,uid,video_id,body)); c.execute("UPDATE videos SET comments=comments+1 WHERE id=?",(video_id,))
    return {"id":cid,"body":body}

@app.post("/api/users/{user_id}/follow")
def follow(user_id:str,authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,"Login required")
    if uid==user_id: raise HTTPException(400,"Cannot follow yourself")
    with db() as c:
        if not c.execute("SELECT 1 FROM users WHERE id=?",(user_id,)).fetchone(): raise HTTPException(404,"User not found")
        exists=c.execute("SELECT 1 FROM follows WHERE follower_id=? AND following_id=?",(uid,user_id)).fetchone()
        if exists:
            c.execute("DELETE FROM follows WHERE follower_id=? AND following_id=?",(uid,user_id)); action="unfollow"; c.execute("UPDATE users SET followers=MAX(followers-1,0) WHERE id=?",(user_id,)); c.execute("UPDATE users SET following=MAX(following-1,0) WHERE id=?",(uid,))
        else:
            c.execute("INSERT INTO follows(follower_id,following_id) VALUES(?,?)",(uid,user_id)); action="follow"; c.execute("UPDATE users SET followers=followers+1 WHERE id=?",(user_id,)); c.execute("UPDATE users SET following=following+1 WHERE id=?",(uid,))
    return {"action":action}

@app.post("/api/events/watch")
def watch(video_id:str,seconds:float=0,action:str="view",authorization:str|None=Header(default=None)):
    uid=current_user(authorization) or "anonymous"
    with db() as c:
        c.execute("INSERT INTO events(id,user_id,video_id,action,seconds) VALUES(?,?,?,?,?)",(uuid4().hex,uid,video_id,action,max(0,seconds)))
        if action=="view": c.execute("UPDATE videos SET views=views+1 WHERE id=?",(video_id,))
    return {"accepted":True}
