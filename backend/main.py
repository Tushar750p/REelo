from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from uuid import uuid4
import hashlib, hmac, os, secrets
from database_gateway import db
from automated_moderation import moderate_text

ROOT=Path(__file__).parent
MEDIA=ROOT/"media"
MEDIA.mkdir(exist_ok=True)
SECRET=os.getenv("REELO_SECRET","change-this-in-production").encode()
MAX_VIDEO_BYTES=100*1024*1024
app=FastAPI(title="REelo API",version="0.7.0")
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","*").split(","),allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.mount("/media",StaticFiles(directory=MEDIA),name="media")

def hash_password(p):
    s=secrets.token_bytes(16); return s.hex()+":"+hashlib.pbkdf2_hmac("sha256",p.encode(),s,120000).hex()
def verify_password(p,x):
    s,d=x.split(":",1); return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256",p.encode(),bytes.fromhex(s),120000).hex(),d)
def token_for(uid):
    p=uid.encode().hex(); return p+"."+hmac.new(SECRET,p.encode(),hashlib.sha256).hexdigest()
def current_user(a):
    if not a or not a.lower().startswith("bearer "): return None
    try:
        p,s=a.split(" ",1)[1].split(".",1); return bytes.fromhex(p).decode() if hmac.compare_digest(s,hmac.new(SECRET,p.encode(),hashlib.sha256).hexdigest()) else None
    except (ValueError,UnicodeDecodeError): return None
def public_user(r): return {"id":r["id"],"username":r["username"],"display_name":r["display_name"],"bio":r["bio"],"followers":r["followers"],"following":r["following"]}
def add_notification(c,recipient_id,actor_id,type_,video_id=None):
    if not recipient_id or recipient_id==actor_id:return
    c.execute("INSERT INTO notifications(id,recipient_id,actor_id,type,video_id) VALUES(?,?,?,?,?)",(uuid4().hex,recipient_id,actor_id,type_,video_id))
def enforce_text(text,content_type):
    result=moderate_text(text)
    if result.get("action") in {"review","limit"}: raise HTTPException(400,f"{content_type.capitalize()} blocked by safety checks")
    return result

def init_db():
    with db() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,display_name TEXT NOT NULL,bio TEXT DEFAULT '',followers INTEGER DEFAULT 0,following INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,filename TEXT NOT NULL,caption TEXT DEFAULT '',likes INTEGER DEFAULT 0,comments INTEGER DEFAULT 0,views INTEGER DEFAULT 0,file_size INTEGER DEFAULT 0,mime_type TEXT DEFAULT '',status TEXT DEFAULT 'ready',created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS likes(user_id TEXT,video_id TEXT,PRIMARY KEY(user_id,video_id));CREATE TABLE IF NOT EXISTS follows(follower_id TEXT,following_id TEXT,PRIMARY KEY(follower_id,following_id));CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY,user_id TEXT,video_id TEXT,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,user_id TEXT,video_id TEXT,action TEXT,seconds REAL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,recipient_id TEXT NOT NULL,actor_id TEXT NOT NULL,type TEXT NOT NULL,video_id TEXT,read INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);""")
        if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():c.execute("INSERT INTO users(id,username,password_hash,display_name,bio) VALUES(?,?,?,?,?)",("demo-user","reelo_creator",hash_password("demo"),"REelo Creator","Create. Watch. Connect."))

@app.on_event("startup")
def startup():init_db()
