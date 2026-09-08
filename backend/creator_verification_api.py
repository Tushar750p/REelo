from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone
from main import db, current_user

router=APIRouter(prefix='/api/creator/verification',tags=['creator-verification'])
class VerifyRequest(BaseModel): legal_name:str; country:str='IN'
def tables(c): c.execute("CREATE TABLE IF NOT EXISTS creator_verifications(id TEXT PRIMARY KEY,user_id TEXT UNIQUE NOT NULL,legal_name TEXT NOT NULL,country TEXT NOT NULL DEFAULT 'IN',status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
def uid(auth):
    x=current_user(auth)
    if not x: raise HTTPException(401,'Login required')
    return str(x)
def now(): return datetime.now(timezone.utc).isoformat()
@router.get('')
def get_verification(authorization:str|None=Header(default=None)):
    u=uid(authorization)
    with db() as c:
        tables(c); r=c.execute('SELECT id,legal_name,country,status,created_at,updated_at FROM creator_verifications WHERE user_id=?',(u,)).fetchone()
    return {'status':r['status'] if r else 'not_started','verification':dict(r) if r else None}
@router.post('')
def submit(data:VerifyRequest,authorization:str|None=Header(default=None)):
    u=uid(authorization); name=data.legal_name.strip(); country=data.country.strip().upper()
    if len(name)<2 or len(name)>120: raise HTTPException(400,'Invalid legal name')
    if len(country)!=2: raise HTTPException(400,'Invalid country code')
    t=now(); vid=uuid4().hex
    with db() as c:
        tables(c); old=c.execute('SELECT status FROM creator_verifications WHERE user_id=?',(u,)).fetchone()
        if old and old['status']=='approved': return {'ok':True,'status':'approved'}
        c.execute("INSERT INTO creator_verifications(id,user_id,legal_name,country,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET legal_name=excluded.legal_name,country=excluded.country,status='pending',updated_at=excluded.updated_at",(vid,u,name,country,'pending',t,t))
    return {'ok':True,'status':'pending','note':'Verification is queued for admin review.'}
