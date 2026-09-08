from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone
import os
from main import db, current_user
from notifications import ensure_notifications_table

router=APIRouter(prefix='/api/creator/verification',tags=['creator-verification'])
class VerifyRequest(BaseModel): legal_name:str; country:str='IN'
class KycStartRequest(BaseModel): provider:str='stripe_identity'

def tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS creator_verifications(id TEXT PRIMARY KEY,user_id TEXT UNIQUE NOT NULL,legal_name TEXT NOT NULL,country TEXT NOT NULL DEFAULT 'IN',status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    # KYC metadata only: REelo never stores identity-document images or document numbers.
    cols={r[1] for r in c.execute('PRAGMA table_info(creator_verifications)').fetchall()}
    for name,typ,default in [('kyc_status','TEXT','not_started'),('kyc_provider','TEXT',''),('kyc_reference','TEXT','')]:
        if name not in cols: c.execute(f"ALTER TABLE creator_verifications ADD COLUMN {name} {typ} DEFAULT '{default}'")

def review_tables(c): c.execute("CREATE TABLE IF NOT EXISTS creator_verification_reviews(id TEXT PRIMARY KEY,verification_id TEXT NOT NULL,admin_id TEXT NOT NULL,status TEXT NOT NULL,reason TEXT DEFAULT '',created_at TEXT NOT NULL)")
def uid(auth):
    x=current_user(auth)
    if not x: raise HTTPException(401,'Login required')
    return str(x)
def now(): return datetime.now(timezone.utc).isoformat()

def notification(c,u,typ):
    ensure_notifications_table(c)
    c.execute("INSERT INTO notifications(id,recipient_id,actor_id,type,video_id) VALUES(?,?,?,?,?)",(uuid4().hex,u,u,typ,None))

@router.get('')
def get_verification(authorization:str|None=Header(default=None)):
    u=uid(authorization)
    with db() as c:
        tables(c); review_tables(c)
        r=c.execute('SELECT id,legal_name,country,status,kyc_status,kyc_provider,kyc_reference,created_at,updated_at FROM creator_verifications WHERE user_id=?',(u,)).fetchone()
        result={'status':r['status'] if r else 'not_started','verification':dict(r) if r else None,'latest_review':None}
        if r:
            review=c.execute("SELECT status,reason,created_at FROM creator_verification_reviews WHERE verification_id=? ORDER BY created_at DESC LIMIT 1",(r['id'],)).fetchone()
            if review: result['latest_review']=dict(review)
            ensure_notifications_table(c)
            n=c.execute("SELECT id,type,read,created_at FROM notifications WHERE recipient_id=? AND type LIKE 'verification_%' ORDER BY created_at DESC LIMIT 10",(u,)).fetchall()
            result['notifications']=[dict(x) for x in n]
    return result

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
        notification(c,u,'verification_submitted')
    return {'ok':True,'status':'pending','note':'Verification is queued for identity review.'}

@router.post('/kyc/start')
def start_kyc(data:KycStartRequest,authorization:str|None=Header(default=None)):
    u=uid(authorization); provider=data.provider.strip().lower()
    if provider not in {'stripe_identity','persona'}: raise HTTPException(400,'Unsupported KYC provider')
    if not os.getenv('REELO_KYC_PROVIDER_KEY'):
        raise HTTPException(503,'KYC provider is not configured. Add REELO_KYC_PROVIDER_KEY before enabling live identity verification.')
    with db() as c:
        tables(c); r=c.execute('SELECT id,status FROM creator_verifications WHERE user_id=?',(u,)).fetchone()
        if not r: raise HTTPException(400,'Submit creator verification details first')
        if r['status']=='approved': return {'ok':True,'status':'approved'}
        ref='kyc_'+uuid4().hex
        c.execute("UPDATE creator_verifications SET kyc_status='started',kyc_provider=?,kyc_reference=?,updated_at=? WHERE user_id=?",(provider,ref,now(),u))
        notification(c,u,'verification_kyc_started')
    # Provider-specific session creation belongs here. No identity documents are stored by REelo.
    return {'ok':True,'status':'started','provider':provider,'reference':ref,'integration':'provider_session_required'}

@router.post('/kyc/webhook')
def kyc_webhook(authorization:str|None=Header(default=None)):
    # Provider webhooks must be authenticated by the provider signature before deployment.
    if authorization != os.getenv('REELO_KYC_WEBHOOK_TOKEN'):
        raise HTTPException(401,'Invalid KYC webhook authorization')
    return {'ok':True,'note':'Provider webhook endpoint reserved for signed KYC status events.'}
