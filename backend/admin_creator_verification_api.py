from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from main import db, current_user
from creator_verification_api import tables
from notifications import ensure_notifications_table
from uuid import uuid4

router = APIRouter(prefix='/api/admin/creator-verification', tags=['admin-creator-verification'])

class StatusRequest(BaseModel):
    status: str
    reason: str = ''

def require_admin(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, 'Login required')
    import os
    allowed = {x.strip() for x in os.getenv('REELO_ADMIN_USER_IDS', '').split(',') if x.strip()}
    if uid not in allowed:
        raise HTTPException(403, 'Admin access required')
    return uid

def ensure_review_tables(c):
    c.execute('''CREATE TABLE IF NOT EXISTS creator_verification_reviews(
        id TEXT PRIMARY KEY, verification_id TEXT NOT NULL, admin_user_id TEXT NOT NULL,
        previous_status TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL)''')

def kyc_state(r):
    return str(r['kyc_status'] or 'not_started').strip().lower()

@router.get('')
def list_verifications(status: str = 'pending', limit: int = 100, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    status = status.strip().lower()
    if status not in {'pending', 'approved', 'rejected', 'all'}:
        raise HTTPException(400, 'Invalid verification status')
    limit = max(1, min(limit, 200))
    with db() as c:
        tables(c); ensure_review_tables(c)
        query = 'SELECT id,user_id,legal_name,country,status,kyc_status,kyc_provider,kyc_reference,created_at,updated_at FROM creator_verifications'
        args = []
        if status != 'all': query += ' WHERE status=?'; args.append(status)
        query += ' ORDER BY updated_at DESC LIMIT ?'; args.append(limit)
        rows = c.execute(query, tuple(args)).fetchall()
    return {'items': [dict(r) for r in rows]}

@router.get('/{verification_id}/history')
def review_history(verification_id: str, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as c:
        tables(c); ensure_review_tables(c)
        row = c.execute('SELECT id FROM creator_verifications WHERE id=?', (verification_id,)).fetchone()
        if not row: raise HTTPException(404, 'Verification request not found')
        rows = c.execute('SELECT id,admin_user_id,previous_status,status,reason,created_at FROM creator_verification_reviews WHERE verification_id=? ORDER BY created_at DESC', (verification_id,)).fetchall()
    return {'items': [dict(r) for r in rows]}

@router.post('/{verification_id}/status')
def update_verification(verification_id: str, body: StatusRequest, authorization: str | None = Header(default=None)):
    admin_id = require_admin(authorization)
    target = body.status.strip().lower(); reason = body.reason.strip()
    if target not in {'pending', 'approved', 'rejected'}: raise HTTPException(400, 'Invalid verification status')
    if len(reason) > 500: raise HTTPException(400, 'Reason is too long')
    if target == 'rejected' and len(reason) < 3: raise HTTPException(400, 'A rejection reason is required')
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        tables(c); ensure_review_tables(c); ensure_notifications_table(c)
        row = c.execute('SELECT id,user_id,status,kyc_status,kyc_provider,kyc_reference FROM creator_verifications WHERE id=?', (verification_id,)).fetchone()
        if not row: raise HTTPException(404, 'Verification request not found')
        current = row['status']
        kyc = kyc_state(row)
        if target == 'approved' and kyc != 'verified':
            raise HTTPException(409, f'Identity verification must be verified before creator approval (current KYC status: {kyc})')
        if current == 'approved' and target != 'approved': raise HTTPException(409, 'Approved verification cannot be changed here')
        c.execute('UPDATE creator_verifications SET status=?,updated_at=? WHERE id=?', (target, now, verification_id))
        c.execute('INSERT INTO creator_verification_reviews(id,verification_id,admin_user_id,previous_status,status,reason,created_at) VALUES(?,?,?,?,?,?,?)', (str(uuid4()), verification_id, admin_id, current, target, reason, now))
        if target in {'approved','rejected'} and current != target:
            c.execute('INSERT INTO notifications(id,recipient_id,actor_id,type,video_id) VALUES(?,?,?,?,?)', (uuid4().hex, row['user_id'], admin_id, 'verification_'+target, None))
    return {'ok': True, 'id': verification_id, 'previous_status': current, 'status': target, 'reason': reason, 'kyc_status': kyc}
