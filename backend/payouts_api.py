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


def live_coin_balance(c, uid):
    c.execute("CREATE TABLE IF NOT EXISTS live_creator_earnings(id INTEGER PRIMARY KEY AUTOINCREMENT,room_id TEXT NOT NULL,creator_id TEXT NOT NULL,sender_id TEXT NOT NULL,gift_id TEXT NOT NULL,gross_coins INTEGER NOT NULL,creator_coins INTEGER NOT NULL,platform_coins INTEGER NOT NULL,created_at TEXT NOT NULL)")
    row = c.execute("SELECT COALESCE(SUM(creator_coins),0) FROM live_creator_earnings WHERE creator_id=?", (uid,)).fetchone()
    return int(row[0] or 0)


@router.get('/summary')
def payout_summary(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid: raise HTTPException(401, 'Login required')
    with db() as c:
        dashboard = build_dashboard(c, uid)
        video_available = balance_cents(c, uid)
        live_coins = live_coin_balance(c, uid)
        ensure_payout_tables(c)
        pending = c.execute("SELECT COALESCE(SUM(amount_cents),0) FROM payout_requests WHERE user_id=? AND status IN ('pending','processing')", (uid,)).fetchone()[0]
    return {'video_earnings_cents': int(dashboard.get('estimated_earnings_cents',0) or 0), 'video_available_cents': video_available, 'live_creator_coins': live_coins, 'pending_payout_cents': int(pending or 0), 'minimum_payout_cents': MIN_PAYOUT_CENTS, 'monetization_eligible': bool(dashboard.get('eligible')), 'verification_status': dashboard.get('verification_status','not_started'), 'live_payout_conversion': None, 'note': 'LIVE gift earnings are shown in creator coins and are not converted to INR until a verified payout policy is configured.'}


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
    kind = data.method_type.strip().lower(); identifier = data.identifier.strip()
    if kind not in {'upi','bank'}: raise HTTPException(400, 'Unsupported payout method')
    if len(identifier) < 4 or len(identifier) > 120: raise HTTPException(400, 'Invalid payout identifier')
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
        if dashboard.get('verification_status') != 'approved': raise HTTPException(403, 'Creator verification must be approved before requesting a payout')
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
