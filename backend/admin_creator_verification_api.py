from fastapi import APIRouter, Header, HTTPException
from main import db, current_user
from creator_verification_api import tables

router = APIRouter(prefix='/api/admin/creator-verification', tags=['admin-creator-verification'])


def require_admin(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, 'Login required')
    import os
    allowed = {x.strip() for x in os.getenv('REELO_ADMIN_USER_IDS', '').split(',') if x.strip()}
    if uid not in allowed:
        raise HTTPException(403, 'Admin access required')
    return uid


@router.get('')
def list_verifications(status: str = 'pending', limit: int = 100, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    status = status.strip().lower()
    if status not in {'pending', 'approved', 'rejected', 'all'}:
        raise HTTPException(400, 'Invalid verification status')
    limit = max(1, min(limit, 200))
    with db() as c:
        tables(c)
        if status == 'all':
            rows = c.execute('SELECT id,user_id,legal_name,country,status,created_at,updated_at FROM creator_verifications ORDER BY updated_at DESC LIMIT ?', (limit,)).fetchall()
        else:
            rows = c.execute('SELECT id,user_id,legal_name,country,status,created_at,updated_at FROM creator_verifications WHERE status=? ORDER BY updated_at DESC LIMIT ?', (status, limit)).fetchall()
    return {'items': [dict(r) for r in rows]}


@router.post('/{verification_id}/status')
def update_verification(verification_id: str, status: str, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    target = status.strip().lower()
    if target not in {'pending', 'approved', 'rejected'}:
        raise HTTPException(400, 'Invalid verification status')
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        tables(c)
        row = c.execute('SELECT id,status FROM creator_verifications WHERE id=?', (verification_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Verification request not found')
        current = row['status']
        if current == 'approved' and target != 'approved':
            raise HTTPException(409, 'Approved verification cannot be changed here')
        c.execute('UPDATE creator_verifications SET status=?,updated_at=? WHERE id=?', (target, now, verification_id))
    return {'ok': True, 'id': verification_id, 'previous_status': current, 'status': target}
