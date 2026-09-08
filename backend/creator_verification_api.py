from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone
import os, json, time, hmac, hashlib, urllib.request
from main import db, current_user
from notifications import ensure_notifications_table

router=APIRouter(prefix='/api/creator/verification',tags=['creator-verification'])
class VerifyRequest(BaseModel): legal_name:str; country:str='IN'
class KycStartRequest(BaseModel): provider:str='persona'

PERSONA_API='https://api.withpersona.com/api/v1'

def tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS creator_verifications(id TEXT PRIMARY KEY,user_id TEXT UNIQUE NOT NULL,legal_name TEXT NOT NULL,country TEXT NOT NULL DEFAULT 'IN',status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    cols={r[1] for r in c.execute('PRAGMA table_info(creator_verifications)').fetchall()}
    for name,typ,default in [('kyc_status','TEXT','not_started'),('kyc_provider','TEXT',''),('kyc_reference','TEXT',''),('kyc_verification_url','TEXT','')]:
        if name not in cols: c.execute(f"ALTER TABLE creator_verifications ADD COLUMN {name} {typ} DEFAULT '{default}'")
    c.execute("CREATE TABLE IF NOT EXISTS kyc_webhook_events(event_id TEXT PRIMARY KEY,provider TEXT NOT NULL,event_name TEXT NOT NULL,created_at TEXT NOT NULL)")

def review_tables(c): c.execute("CREATE TABLE IF NOT EXISTS creator_verification_reviews(id TEXT PRIMARY KEY,verification_id TEXT NOT NULL,admin_id TEXT NOT NULL,status TEXT NOT NULL,reason TEXT DEFAULT '',created_at TEXT NOT NULL)")
def uid(auth):
    x=current_user(auth)
    if not x: raise HTTPException(401,'Login required')
    return str(x)
def now(): return datetime.now(timezone.utc).isoformat()

def notification(c,u,typ):
    ensure_notifications_table(c)
    c.execute("INSERT INTO notifications(id,recipient_id,actor_id,type,video_id) VALUES(?,?,?,?,?)",(uuid4().hex,u,u,typ,None))

def persona_request(method,path,payload=None):
    key=os.getenv('PERSONA_API_KEY','').strip()
    if not key: raise HTTPException(503,'Persona KYC is not configured')
    body=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(PERSONA_API+path,data=body,method=method,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Persona-Version':os.getenv('PERSONA_VERSION','2025-12-08')})
    try:
        with urllib.request.urlopen(req,timeout=12) as r: return json.loads(r.read().decode())
    except Exception as e:
        code=getattr(e,'code',502)
        raise HTTPException(502,f'Persona request failed ({code})')

def persona_signature_valid(raw:bytes,header:str,secret:str):
    if not header or not secret: return False
    parts=[]
    for token in header.replace(',',' ').split():
        if '=' in token:
            k,v=token.split('=',1); parts.append((k.strip(),v.strip()))
    timestamps=[v for k,v in parts if k=='t' and v.isdigit()]
    if not timestamps: return False
    # Persona signatures are timestamped; accept a valid current timestamp and any
    # matching v1 signature so secret rotation can be handled safely.
    ts=timestamps[0]
    if abs(int(time.time())-int(ts))>300: return False
    expected=hmac.new(secret.encode(),(ts+'.').encode()+raw,hashlib.sha256).hexdigest()
    return any(k=='v1' and hmac.compare_digest(expected,v) for k,v in parts)

@router.get('')
def get_verification(authorization:str|None=Header(default=None)):
    u=uid(authorization)
    with db() as c:
        tables(c); review_tables(c)
        r=c.execute('SELECT id,legal_name,country,status,kyc_status,kyc_provider,kyc_reference,kyc_verification_url,created_at,updated_at FROM creator_verifications WHERE user_id=?',(u,)).fetchone()
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
    if provider!='persona': raise HTTPException(400,'Only Persona KYC is enabled')
    template=os.getenv('PERSONA_INQUIRY_TEMPLATE_ID','').strip()
    if not os.getenv('PERSONA_API_KEY','').strip() or not template:
        raise HTTPException(503,'Persona KYC is not configured. Add PERSONA_API_KEY and PERSONA_INQUIRY_TEMPLATE_ID.')
    with db() as c:
        tables(c); r=c.execute('SELECT id,status,kyc_status,kyc_reference,kyc_verification_url FROM creator_verifications WHERE user_id=?',(u,)).fetchone()
        if not r: raise HTTPException(400,'Submit creator verification details first')
        if r['status']=='approved': return {'ok':True,'status':'approved'}
        if r['kyc_status']=='verified': return {'ok':True,'status':'verified','reference':r['kyc_reference'],'verification_url':r['kyc_verification_url']}
        if r['kyc_status']=='started' and r['kyc_verification_url']:
            return {'ok':True,'status':'started','provider':'persona','reference':r['kyc_reference'],'inquiry_id':r['kyc_reference'],'verification_url':r['kyc_verification_url'],'resume':True}
        reference='reelo_'+uuid4().hex
    payload={'data':{'attributes':{'inquiry-template-id':template,'reference-id':reference}}}
    result=persona_request('POST','/inquiries',payload)
    pdata=result.get('data') or {}; meta=result.get('meta') or {}; inquiry_id=pdata.get('id'); status=(pdata.get('attributes') or {}).get('status','pending')
    link=meta.get('one-time-link') or meta.get('one-time-link-short')
    if not inquiry_id: raise HTTPException(502,'Persona returned no inquiry ID')
    with db() as c:
        tables(c)
        c.execute("UPDATE creator_verifications SET kyc_status=?,kyc_provider='persona',kyc_reference=?,kyc_verification_url=?,updated_at=? WHERE user_id=?",('started',inquiry_id,link or '',now(),u))
        notification(c,u,'verification_kyc_started')
    return {'ok':True,'status':'started','provider':'persona','reference':inquiry_id,'inquiry_id':inquiry_id,'status_from_provider':status,'verification_url':link}

@router.post('/kyc/webhook')
async def kyc_webhook(request:Request,persona_signature:str|None=Header(default=None,alias='Persona-Signature')):
    secret=os.getenv('PERSONA_WEBHOOK_SECRET','').strip()
    raw=await request.body()
    if not persona_signature_valid(raw,persona_signature or '',secret):
        raise HTTPException(401,'Invalid Persona webhook signature')
    try: body=json.loads(raw.decode())
    except Exception: raise HTTPException(400,'Invalid JSON')
    event=body.get('data') or {}; event_id=event.get('id'); attrs=event.get('attributes') or {}; event_name=attrs.get('name','')
    payload=attrs.get('payload') or {}; pdata=payload.get('data') or {}; p_attrs=pdata.get('attributes') or {}
    inquiry_id=pdata.get('id'); status=p_attrs.get('status')
    if not event_id or not inquiry_id: return {'ok':True,'ignored':True}
    with db() as c:
        tables(c)
        exists=c.execute('SELECT 1 FROM kyc_webhook_events WHERE event_id=?',(event_id,)).fetchone()
        if exists: return {'ok':True,'duplicate':True}
        c.execute('INSERT INTO kyc_webhook_events(event_id,provider,event_name,created_at) VALUES(?,?,?,?)',(event_id,'persona',event_name,now()))
        row=c.execute('SELECT user_id FROM creator_verifications WHERE kyc_provider=? AND kyc_reference=?',('persona',inquiry_id)).fetchone()
        if not row: return {'ok':True,'ignored':True}
        u=row['user_id']
        if event_name=='inquiry.approved' or status=='approved':
            new='verified'; note='verification_kyc_verified'
        elif event_name in {'inquiry.declined','inquiry.failed'} or status in {'declined','failed'}:
            new='failed'; note='verification_kyc_failed'
        elif event_name=='inquiry.expired' or status=='expired':
            new='expired'; note='verification_kyc_expired'
        elif event_name=='inquiry.marked-for-review' or status=='needs_review':
            new='review'; note='verification_kyc_review'
        elif event_name in {'inquiry.started','inquiry.completed'} or status in {'pending','completed'}:
            new='started'; note=None
        else:
            new=None; note=None
        if new:
            c.execute('UPDATE creator_verifications SET kyc_status=?,updated_at=? WHERE user_id=?', (new,now(),u))
            if note: notification(c,u,note)
    return {'ok':True,'event':event_name,'status':status}
