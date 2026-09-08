from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from pathlib import Path
from uuid import uuid4
import subprocess, shutil

from main import current_user, db, MEDIA, MAX_VIDEO_BYTES

router=APIRouter(prefix="/api/editor",tags=["editor"])

def user(a):
    uid=current_user(a)
    if not uid: raise HTTPException(401,"Login required")
    return uid

def num(value,default=0.0):
    try:return float(value) if value not in (None,"") else default
    except ValueError: raise HTTPException(400,"Invalid editor value")

@router.post("/publish")
async def publish_editor(file:UploadFile=File(...),caption:str=Form(""),start:str=Form(""),end:str=Form(""),speed:str=Form("1"),filter_name:str=Form("none"),rotate:str=Form("0"),flip:str=Form("false"),mute:str=Form("false"),sound_id:str=Form(""),authorization:str|None=Header(default=None)):
    uid=user(authorization)
    ext=Path(file.filename or "video.mp4").suffix.lower()
    if ext not in {".mp4",".mov",".webm",".m4v"}: raise HTTPException(415,"Unsupported video format")
    src=MEDIA/f"editor-src-{uuid4().hex}{ext}"; out=MEDIA/f"{uuid4().hex}.mp4"; total=0
    try:
        with src.open("wb") as f:
            while chunk:=await file.read(1024*1024):
                total+=len(chunk)
                if total>MAX_VIDEO_BYTES: raise HTTPException(413,"Video is too large. Maximum size is 100 MB.")
                f.write(chunk)
        if not total: raise HTTPException(400,"Empty video file")
        if not shutil.which("ffmpeg"): raise HTTPException(503,"Video processing is unavailable on this server")
        s,e=num(start,None),num(end,None)
        if s is not None and s<0: raise HTTPException(400,"Invalid trim start")
        if e is not None and e<=0: raise HTTPException(400,"Invalid trim end")
        if s is not None and e is not None and e<=s: raise HTTPException(400,"Trim end must be after start")
        sp=num(speed,1); 
        if sp<=0 or sp>4: raise HTTPException(400,"Speed must be between 0.25 and 4")
        rot=int(num(rotate,0))%360
        if rot not in {0,90,180,270}: raise HTTPException(400,"Rotation must be 0, 90, 180 or 270")
        filters=[]
        if filter_name=="mono": filters.append("hue=s=0")
        elif filter_name=="warm": filters.append("colorbalance=rs=.08:gs=.02:bs=-.04")
        elif filter_name=="cool": filters.append("colorbalance=rs=-.04:gs=.01:bs=.08")
        elif filter_name not in {"none",""}: raise HTTPException(400,"Unsupported filter")
        if rot==90: filters.append("transpose=1")
        elif rot==180: filters.append("hflip,vflip")
        elif rot==270: filters.append("transpose=2")
        if flip.lower()=="true": filters.append("hflip")
        if sp!=1: filters.append(f"setpts={1/sp}*PTS")
        cmd=["ffmpeg","-y","-i",str(src)]
        if s is not None: cmd += ["-ss",str(s)]
        if e is not None and s is not None: cmd += ["-t",str(e-s)]
        elif e is not None: cmd += ["-to",str(e)]
        if filters: cmd += ["-vf",",".join(filters)]
        if mute.lower()=="true": cmd += ["-an"]
        cmd += ["-c:v","libx264","-preset","veryfast","-crf","23","-movflags","+faststart"]
        if sp!=1: cmd += ["-af",f"atempo={min(sp,2)}"]
        cmd += [str(out)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
        if p.returncode!=0: raise HTTPException(422,"Video processing failed")
        size=out.stat().st_size
        vid=uuid4().hex
        with db() as c:
            c.execute("INSERT INTO videos(id,user_id,filename,caption,file_size,mime_type,status) VALUES(?,?,?,?,?,?,?)",(vid,uid,out.name,caption.strip()[:2200],size,"video/mp4","ready"))
            if sound_id:
                c.execute("CREATE TABLE IF NOT EXISTS video_sounds(video_id TEXT PRIMARY KEY,sound_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
                if c.execute("SELECT id FROM sounds WHERE id=?",(sound_id,)).fetchone(): c.execute("INSERT OR REPLACE INTO video_sounds(video_id,sound_id) VALUES(?,?)",(vid,sound_id))
        return {"id":vid,"status":"ready","url":f"/media/{out.name}","size":size}
    finally:
        src.unlink(missing_ok=True)
