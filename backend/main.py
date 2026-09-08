from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from uuid import uuid4
import hashlib, hmac, os, secrets, sqlite3
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

class Credentials(BaseModel): username:str; password:str; display_name:str|None=None
class ProfileUpdate(BaseModel): display_name:str|None=None; bio:str|None=None
class CommentIn(BaseModel): body:str

@app.on_event("startup")
def startup():init_db()
@app.get("/health")
def health():return {"status":"ok","service":"reelo-api","version":app.version}
@app.post("/api/auth/register")
def register(data:Credentials):
    u=data.username.strip().lower()
    if len(u)<3 or len(u)>30 or len(data.password)<6 or not u.replace("_","").isalnum():raise HTTPException(400,"Invalid username or password")
    uid=uuid4().hex
    try:
        with db() as c:c.execute("INSERT INTO users(id,username,password_hash,display_name) VALUES(?,?,?,?)",(uid,u,hash_password(data.password),data.display_name.strip() if data.display_name else u))
    except Exception as exc:
        if exc.__class__.__name__ in {"IntegrityError","UniqueViolation"}:raise HTTPException(409,"Username already exists")
        raise
    with db() as c:r=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    return {"token":token_for(uid),"user":public_user(r)}
@app.post("/api/auth/login")
def login(data:Credentials):
    with db() as c:r=c.execute("SELECT * FROM users WHERE username=?",(data.username.strip().lower(),)).fetchone()
    if not r or not verify_password(data.password,r["password_hash"]):raise HTTPException(401,"Invalid username or password")
    return {"token":token_for(r["id"]),"user":public_user(r)}
@app.get("/api/me")
def me(authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid:raise HTTPException(401,"Login required")
    with db() as c:
        r=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        if not r:raise HTTPException(401,"Session is invalid")
        unread=c.execute("SELECT COUNT(*) FROM notifications WHERE recipient_id=? AND read=0",(uid,)).fetchone()[0]
    return {"user":public_user(r),"unread_notifications":unread}
@app.patch("/api/me")
def update_me(data:ProfileUpdate,authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid:raise HTTPException(401,"Login required")
    with db() as c:
        r=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        if not r:raise HTTPException(404,"User not found")
        display=(data.display_name if data.display_name is not None else r["display_name"]).strip(); bio=(data.bio if data.bio is not None else r["bio"]).strip()
        if not display or len(display)>80 or len(bio)>160:raise HTTPException(400,"Invalid profile data")
        c.execute("UPDATE users SET display_name=?,bio=? WHERE id=?",(display,bio,uid)); r=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    return {"user":public_user(r)}
def feed_rows(c,uid,limit,following_only=False):
    if following_only:
        if not uid:return []
        return c.execute("SELECT v.*,u.username,u.display_name,CASE WHEN EXISTS(SELECT 1 FROM likes l WHERE l.video_id=v.id AND l.user_id=?) THEN 1 ELSE 0 END liked FROM videos v JOIN users u ON u.id=v.user_id JOIN follows f ON f.following_id=v.user_id AND f.follower_id=? WHERE v.status='ready' ORDER BY v.created_at DESC LIMIT ?",(uid,uid,limit)).fetchall()
    return c.execute("SELECT v.*,u.username,u.display_name,CASE WHEN EXISTS(SELECT 1 FROM likes l WHERE l.video_id=v.id AND l.user_id=?) THEN 1 ELSE 0 END liked FROM videos v JOIN users u ON u.id=v.user_id WHERE v.status='ready' ORDER BY v.created_at DESC LIMIT ?",(uid,limit)).fetchall()
@app.get("/api/feed")
def feed(limit:int=20,following:bool=False,mode:str|None=None,authorization:str|None=Header(default=None)):
    if mode is not None:following=mode.strip().lower()=="following"
    uid=current_user(authorization);limit=max(1,min(limit,50))
    with db() as c:r=feed_rows(c,uid,limit,following)
    return {"items":[dict(x) for x in r],"algorithm":"following-v1" if following else "hybrid-v1","following":following}
@app.get("/api/search")
def search(q:str):
    with db() as c:r=c.execute("SELECT v.*,u.username,u.display_name FROM videos v JOIN users u ON u.id=v.user_id WHERE v.status='ready' AND (v.caption LIKE ? OR u.username LIKE ?) ORDER BY v.created_at DESC LIMIT 50",(f"%{q.strip()}%",f"%{q.strip()}%")).fetchall()
    return {"query":q,"items":[dict(x) for x in r]}
@app.post("/api/videos/upload")
async def upload_video(file:UploadFile=File(...),caption:str=Form(""),authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid:raise HTTPException(401,"Login required")
    caption=caption.strip()[:2200]; enforce_text(caption,"caption")
    mime=(file.content_type or "").lower();ext=Path(file.filename or "video.mp4").suffix.lower();allowed={".mp4",".webm",".mov",".m4v"}
    if ext not in allowed or not mime.startswith("video/"):raise HTTPException(415,"Unsupported video format")
    total=0;name=f"{uuid4().hex}{ext}";dest=MEDIA/name
    try:
        with dest.open("wb") as out:
            while chunk:=await file.read(1024*1024):
                total+=len(chunk)
                if total>MAX_VIDEO_BYTES:raise HTTPException(413,"Video is too large. Maximum size is 100 MB.")
                out.write(chunk)
    except Exception:dest.unlink(missing_ok=True);raise
    if not total:dest.unlink(missing_ok=True);raise HTTPException(400,"Empty video file")
    vid=uuid4().hex
    with db() as c:c.execute("INSERT INTO videos(id,user_id,filename,caption,file_size,mime_type,status) VALUES(?,?,?,?,?,?,?)",(vid,uid,name,caption,total,mime,"ready"))
    return {"id":vid,"status":"uploaded","filename":name,"size":total,"mime_type":mime,"url":f"/media/{name}"}
@app.post("/api/videos/{video_id}/like")
def like(video_id:str,authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid:raise HTTPException(401,"Login required")
    with db() as c:
        video=c.execute("SELECT user_id FROM videos WHERE id=?",(video_id,)).fetchone()
        if not video:raise HTTPException(404,"Video not found")
        x=c.execute("SELECT 1 FROM likes WHERE user_id=? AND video_id=?",(uid,video_id)).fetchone()
        if x:c.execute("DELETE FROM likes WHERE user_id=? AND video_id=?",(uid,video_id));c.execute("UPDATE videos SET likes=MAX(likes-1,0) WHERE id=?",(video_id,));liked=False
        else:c.execute("INSERT INTO likes(user_id,video_id) VALUES(?,?)",(uid,video_id));c.execute("UPDATE videos SET likes=likes+1 WHERE id=?",(video_id,));liked=True;add_notification(c,video["user_id"],uid,"like",video_id)
        n=c.execute("SELECT likes FROM videos WHERE id=?",(video_id,)).fetchone()[0]
    return {"liked":liked,"likes":n}
@app.get("/api/videos/{video_id}/comments")
def list_comments(video_id:str,limit:int=50,offset:int=0):
    limit=max(1,min(limit,100));offset=max(0,offset)
    with db() as c:
        if not c.execute("SELECT 1 FROM videos WHERE id=?",(video_id,)).fetchone():raise HTTPException(404,"Video not found")
        r=c.execute("SELECT c.id,c.body,c.created_at,u.id user_id,u.username,u.display_name FROM comments c JOIN users u ON u.id=c.user_id WHERE c.video_id=? ORDER BY c.created_at DESC LIMIT ? OFFSET ?",(video_id,limit,offset)).fetchall();total=c.execute("SELECT COUNT(*) FROM comments WHERE video_id=?",(video_id,)).fetchone()[0]
    return {"items":[dict(x) for x in r],"total":total,"limit":limit,"offset":offset}
@app.post("/api/videos/{video_id}/comments")
def comment(video_id:str,data:CommentIn,authorization:str|None=Header(default=None)):
    uid=current_user(authorization);body=data.body.strip()
    if not uid:raise HTTPException(401,"Login required")
    if not body or len(body)>500:raise HTTPException(400,"Comment must be 1-500 characters")
    enforce_text(body,"comment")
    with db() as c:
        video=c.execute("SELECT user_id FROM videos WHERE id=?",(video_id,)).fetchone()
        if not video:raise HTTPException(404,"Video not found")
        cid=uuid4().hex;c.execute("INSERT INTO comments(id,user_id,video_id,body) VALUES(?,?,?,?)",(cid,uid,video_id,body));c.execute("UPDATE videos SET comments=comments+1 WHERE id=?",(video_id,));add_notification(c,video["user_id"],uid,"comment",video_id);r=c.execute("SELECT c.id,c.body,c.created_at,u.username,u.display_name FROM comments c JOIN users u ON u.id=c.user_id WHERE c.id=?",(cid,)).fetchone()
    return dict(r)
@app.post("/api/users/{user_id}/follow")
def follow(user_id:str,authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid:raise HTTPException(401,"Login required")
    if uid==user_id:raise HTTPException(400,"Cannot follow yourself")
    with db() as c:
        if not c.execute("SELECT 1 FROM users WHERE id=?",(user_id,)).fetchone():raise HTTPException(404,"User not found")
        x=c.execute("SELECT 1 FROM follows WHERE follower_id=? AND following_id=?",(uid,user_id)).fetchone()
        if x:c.execute("DELETE FROM follows WHERE follower_id=? AND following_id=?",(uid,user_id));a="unfollow";c.execute("UPDATE users SET followers=MAX(followers-1,0) WHERE id=?",(user_id,));c.execute("UPDATE users SET following=MAX(following-1,0) WHERE id=?",(uid,))
        else:c.execute("INSERT INTO follows(follower_id,following_id) VALUES(?,?)",(uid,user_id));a="follow";c.execute("UPDATE users SET followers=followers+1 WHERE id=?",(user_id,));c.execute("UPDATE users SET following=following+1 WHERE id=?",(uid,));add_notification(c,user_id,uid,"follow")
    return {"action":a}
@app.get("/api/notifications")
def notifications(limit:int=50,offset:int=0,authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid:raise HTTPException(401,"Login required")
    limit=max(1,min(limit,100));offset=max(0,offset)
    with db() as c:
        rows=c.execute("SELECT n.id,n.type,n.video_id,n.read,n.created_at,u.id actor_id,u.username actor_username,u.display_name actor_display_name FROM notifications n JOIN users u ON u.id=n.actor_id WHERE n.recipient_id=? ORDER BY n.created_at DESC LIMIT ? OFFSET ?",(uid,limit,offset)).fetchall();unread=c.execute("SELECT COUNT(*) FROM notifications WHERE recipient_id=? AND read=0",(uid,)).fetchone()[0];total=c.execute("SELECT COUNT(*) FROM notifications WHERE recipient_id=?",(uid,)).fetchone()[0]
    return {"items":[dict(x) for x in rows],"unread":unread,"total":total,"limit":limit,"offset":offset}
@app.post("/api/notifications/read-all")
def mark_all_notifications_read(authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid:raise HTTPException(401,"Login required")
    with db() as c:c.execute("UPDATE notifications SET read=1 WHERE recipient_id=? AND read=0",(uid,))
    return {"updated":True,"unread":0}
@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id:str,authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid:raise HTTPException(401,"Login required")
    with db() as c:
        cur=c.execute("UPDATE notifications SET read=1 WHERE id=? AND recipient_id=?",(notification_id,uid))
        if cur.rowcount==0:raise HTTPException(404,"Notification not found")
    return {"updated":True}
@app.post("/api/events/watch")
def watch(video_id:str,seconds:float=0,action:str="view",authorization:str|None=Header(default=None)):
    with db() as c:
        c.execute("INSERT INTO events(id,user_id,video_id,action,seconds) VALUES(?,?,?,?,?)",(uuid4().hex,current_user(authorization) or "anonymous",video_id,action,max(0,seconds)))
        if action=="view":c.execute("UPDATE videos SET views=views+1 WHERE id=?",(video_id,))
    return {"accepted":True}
