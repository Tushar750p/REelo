import os, json, hmac, hashlib, time, urllib.request
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException, Request
from main import db, current_user
from notifications import ensure_notifications_table

router = APIRouter(prefix='/api/creator/kyc', tags=['creator-kyc'])
PERSONA_API = 'https://api.withpersona.com/api/v1/inquiries'

def uid(auth):
    x = current_user(auth)
    if not x:
        raise HTTPException(401, 'Login required')
    return str(x)

def tables(c):
    c.execute('''CREATE TABLE IF NOT EXISTS creator_kyc(
        id TEXT PRIMARY KEY,user_id TEXT UNIQUE NOT NULL,provider TEXT NOT NULL DEFAULT 'persona',
        inquiry_id TEXT UNIQUE,reference_id TEXT UNIQUE,status TEXT NOT NULL DEFAULT 'not_started',
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS creator_kyc_events(
        id TEXT PRIMARY KEY,event_id TEXT UNIQUE,event_type TEXT NOT NULL,inquiry_id TEXT,
        created_at TEXT NOT NULL)''')

def now():
    return __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()

def ensure_row(c, u):
    tables(c)
    r = c.execute('SELECT * FROM creator_kyc WHERE user_id=?', (u,)).fetchone()
    if r: return r
    t = now(); kid = uuid4().hex; ref = 'reelo_' + uuid4().hex
    c.execute('INSERT INTO creator_kyc(id,user_id,provider,reference_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(kid,u,'persona',ref,'not_started',t,t))
    return c.execute('SELECT * FROM creator_kyc WHERE user_id=?',(u,)).fetchone()

@router.get('')
def get_kyc(authorization: str|None = Header(default=None)):
    u = uid(authorization)
    with db() as c:
        r = ensure_row(c,u)
        return {'provider':r['provider'],'status':r['status'],'inquiry_id':r['inquiry_id'],'reference_id':r['reference_id'],'created_at':r['created_at'],'updated_at':r['updated_at']}

@router.post('/start')
def start_kyc(authorization: str|None = Header(default=None)):
    u = uid(authorization)
    key = os.getenv('PERSONA_API_KEY','').strip()
    template = os.getenv('PERSONA_INQUIRY_TEMPLATE_ID','').strip()
    if not key or not template:
        raise HTTPException(503,'Identity verification is not configured yet')
    with db() as c:
        r = ensure_row(c,u)
        if r['status'] == 'approved': return {'ok':True,'status':'approved'}
        if r['inquiry_id'] and r['status'] in ('created','pending','completed','needs_review'):
            raise HTTPException(409,'An identity verification session is already active')
        ref = r['reference_id']
        payload = {'data':{'attributes':{'inquiry-template-id':template,'reference-id':ref}}}
        req = urllib.request.Request(PERSONA_API,data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json','Persona-Version':'2023-01-05'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=15) as resp: data=json.loads(resp.read().decode())
        except Exception as e:
            raise HTTPException(502,'Unable to create identity verification session') from e
        inquiry = data.get('data',{}); inquiry_id=inquiry.get('id'); link=data.get('meta',{}).get('one-time-link')
        if not inquiry_id: raise HTTPException(502,'Identity provider returned an invalid session')
        t=now(); c.execute("UPDATE creator_kyc SET inquiry_id=?,status='created',updated_at=? WHERE user_id=?",(inquiry_id,t,u))
        ensure_notifications_table(c); c.execute("INSERT INTO notifications(id,recipient_id,actor_id,type,video_id) VALUES(?,?,?,?,?)",(uuid4().hex,u,u,'kyc_started',None))
        return {'ok':True,'provider':'persona','status':'created','inquiry_id':inquiry_id,'verification_url':link}

def valid_signature(raw, header, secret):
    if not header or not secret: return False
    try:
        groups = header.split(' '); ts = groups[0].split(',')[0].split('=',1)[1]
        if abs(time.time()-int(ts)) > 300: return False
        expected = hmac.new(secret.encode(), (ts+'.'+raw.decode()).encode(), hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, part.split('v1=',1)[1]) for group in groups for part in group.split(',') if part.startswith('v1='))
    except Exception: return False

@router.post('/webhook')
async def persona_webhook(request: Request, persona_signature: str|None = Header(default=None)):
    raw = await request.body(); secret=os.getenv('PERSONA_WEBHOOK_SECRET','').strip()
    if not valid_signature(raw,persona_signature,secret): raise HTTPException(401,'Invalid webhook signature')
    try: body=json.loads(raw.decode())
    except Exception: raise HTTPException(400,'Invalid JSON')
    event=body.get('data',{}); attrs=event.get('attributes',{}); event_id=event.get('id')
    event_type=attrs.get('name') or attrs.get('event-name') or ''
    payload=attrs.get('payload',{}).get('data',{}) if isinstance(attrs.get('payload'),dict) else {}
    inquiry_id=payload.get('id') if payload.get('type')=='inquiry' else attrs.get('inquiry-id')
    if not inquiry_id: return {'ok':True}
    mapping={'inquiry.created':'created','inquiry.started':'pending','inquiry.completed':'completed','inquiry.approved':'approved','inquiry.declined':'declined','inquiry.marked-for-review':'needs_review','inquiry.expired':'expired','inquiry.failed':'failed'}
    new_status=mapping.get(event_type)
    with db() as c:
        tables(c)
        if event_id and c.execute('SELECT 1 FROM creator_kyc_events WHERE event_id=?',(event_id,)).fetchone(): return {'ok':True,'duplicate':True}
        if event_id: c.execute('INSERT INTO creator_kyc_events(id,event_id,event_type,inquiry_id,created_at) VALUES(?,?,?,?,?)',(uuid4().hex,event_id,event_type,inquiry_id,now()))
        row=c.execute('SELECT user_id,status FROM creator_kyc WHERE inquiry_id=?',(inquiry_id,)).fetchone()
        if row and new_status:
            c.execute('UPDATE creator_kyc SET status=?,updated_at=? WHERE inquiry_id=?',(new_status,now(),inquiry_id))
            if new_status in ('approved','declined','needs_review','failed'):
                ensure_notifications_table(c); c.execute("INSERT INTO notifications(id,recipient_id,actor_id,type,video_id) VALUES(?,?,?,?,?)",(uuid4().hex,row['user_id'],row['user_id'],'kyc_'+new_status,None))
    return {'ok':True}
