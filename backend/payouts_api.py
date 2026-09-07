from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from main import db, current_user
from monetization_api import ensure_monetization_table, build_dashboard

router = APIRouter(prefix="/api/payouts", tags=["payouts"])
MIN_PAYOUT_CENTS = 1000

class PayoutMethod(BaseModel):
    method_type: str
    identifier: str


def ensure_payout_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS payout_methods(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,method_type TEXT NOT NULL,identifier_masked TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS payout_requests(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,amount_cents INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',method_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")


def balance_cents(c, uid):
    ensure_monetization_table(c); ensure_payout_tables(c)
    earned = c.execute("SELECT COALESCE(SUM(amount_cents),0) FROM creator_earnings WHERE user_id=?", (uid,)).fetchone()[0]
    paid = c.execute("SELECT COALESCE(SUM(amount_cents),0) FROM payout_requests WHERE user_id=? AND status IN ('pending','processing','paid')", (uid,)).fetchone()[0]
    return max(0, int(earned or 0) - int(paid or 0))


@router.get('/methods')
def methods(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid: raise HTTPException(401, 'Login required')
    with db() as c:
        ensure_payout_tables(c)
        rows = c.execute('SELECT id,method_type,identifier_masked,created_at FROM payout_methods WHERE user_id=? ORDER BY created_at DESC', (uid,)).fetchall()
    return {'items': [dict(r) for r in rows]}


@router.post('/methods')
def add_method(data: PayoutMethod, authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid: raise HTTPException(401, 'Login required')
    kind = data.method_type.strip().lower()
    identifier = data.identifier.strip()
    if kind not in {'upi','bank'}: raise HTTPException(400, 'Unsupported payout method')
    if len(identifier) < 4 or len(identifier) > 120: raise HTTPException(400, 'Invalid payout identifier')
    # Store only a masked identifier; real payment credentials belong in a payment provider.
    masked = ('*' * max(0, len(identifier) - 4)) + identifier[-4:]
    mid = uuid4().hex
    with db() as c:
        ensure_payout_tables(c)
        c.execute('INSERT INTO payout_methods(id,user_id,method_type,identifier_masked) VALUES(?,?,?,?)', (mid, uid, kind, masked))
    return {'ok': True, 'id': mid, 'method_type': kind, 'identifier_masked': masked}


@router.post('/request')
def request_payout(method_id: str, authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid: raise HTTPException(401, 'Login required')
    with db() as c:
        ensure_payout_tables(c)
        method = c.execute('SELECT id FROM payout_methods WHERE id=? AND user_id=?', (method_id, uid)).fetchone()
        if not method: raise HTTPException(404, 'Payout method not found')
        dashboard = build_dashboard(c, uid)
        if not dashboard['eligible']: raise HTTPException(403, 'Creator is not eligible for monetization')
        amount = balance_cents(c, uid)
        if amount < MIN_PAYOUT_CENTS: raise HTTPException(400, 'Minimum payout balance is ₹10.00')
        request_id = uuid4().hex
        c.execute('INSERT INTO payout_requests(id,user_id,amount_cents,status,method_id) VALUES(?,?,?,?,?)', (request_id, uid, amount, 'pending', method_id))
    return {'ok': True, 'request_id': request_id, 'amount': round(amount / 100, 2), 'status': 'pending', 'note': 'Payment provider integration is required to send funds.'}


@router.get('/requests')
def requests(limit: int = 50, authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid: raise HTTPException(401, 'Login required')
    limit = max(1, min(limit, 100))
    with db() as c:
        ensure_payout_tables(c)
        rows = c.execute('SELECT id,amount_cents,status,method_id,created_at FROM payout_requests WHERE user_id=? ORDER BY created_at DESC LIMIT ?', (uid, limit)).fetchall()
    return {'items': [dict(r) for r in rows]}
