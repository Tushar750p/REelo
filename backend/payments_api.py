import hashlib
import hmac
import os
import time
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from main import db, current_user

router = APIRouter(prefix="/api/payments", tags=["payments"])
PACKAGES = {"starter":100,"creator":550,"popular":1200,"mega":5000}
INR_BY_PACKAGE = {"starter":99,"creator":499,"popular":999,"mega":3999}
PROVIDER = os.getenv("REELO_PAYMENT_PROVIDER", "demo").lower()

class CheckoutRequest(BaseModel):
    package_id: str


def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS payment_orders(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,package_id TEXT NOT NULL,coins INTEGER NOT NULL,amount_paise INTEGER NOT NULL,provider TEXT NOT NULL,provider_order_id TEXT,status TEXT NOT NULL DEFAULT 'created',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")


def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def uid(auth):
    value=current_user(auth)
    if not value: raise HTTPException(401,'Login required')
    return str(value)


@router.get('/config')
def config(authorization: str | None = Header(default=None)):
    uid(authorization)
    return {'provider': PROVIDER, 'live': PROVIDER != 'demo', 'currency':'INR'}


@router.post('/checkout')
def checkout(data: CheckoutRequest, authorization: str | None = Header(default=None)):
    user=uid(authorization); package=data.package_id.strip().lower()
    if package not in PACKAGES: raise HTTPException(400,'Invalid coin package')
    coins=PACKAGES[package]; amount=INR_BY_PACKAGE[package]
    if PROVIDER == 'demo':
        raise HTTPException(409,'Payment provider is not configured. Use the development Coin Store top-up.')
    # Provider-specific SDK/order creation belongs here. Never trust client-supplied amount.
    order_id='reelo_'+uuid4().hex
    t=now()
    with db() as c:
        ensure_tables(c)
        c.execute('INSERT INTO payment_orders(id,user_id,package_id,coins,amount_paise,provider,provider_order_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(order_id,user,package,coins,amount*100,PROVIDER,None,'created',t,t))
    return {'ok':True,'order_id':order_id,'package_id':package,'coins':coins,'amount_inr':amount,'provider':PROVIDER,'status':'created','note':'Complete provider SDK integration before accepting production payments.'}


@router.get('/orders')
def orders(authorization: str | None = Header(default=None)):
    user=uid(authorization)
    with db() as c:
        ensure_tables(c)
        rows=c.execute('SELECT id,package_id,coins,amount_paise,provider,status,created_at,updated_at FROM payment_orders WHERE user_id=? ORDER BY created_at DESC LIMIT 50',(user,)).fetchall()
    return {'items':[dict(r)|{'amount_inr':round(r['amount_paise']/100,2)} for r in rows]}


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature or not secret: return False
    digest=hmac.new(secret.encode(),payload,hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest,signature)


@router.post('/webhook')
async def webhook(request: Request, x_reelo_signature: str | None = Header(default=None)):
    body=await request.body(); secret=os.getenv('REELO_PAYMENT_WEBHOOK_SECRET','')
    if not verify_webhook_signature(body,x_reelo_signature or '',secret): raise HTTPException(401,'Invalid webhook signature')
    data=await request.json(); order_id=str(data.get('order_id','')); status=str(data.get('status','')).lower()
    if status not in {'paid','failed','cancelled'}: raise HTTPException(400,'Unsupported payment status')
    with db() as c:
        ensure_tables(c)
        row=c.execute('SELECT id,user_id,package_id,coins,status FROM payment_orders WHERE id=?',(order_id,)).fetchone()
        if not row: raise HTTPException(404,'Order not found')
        if row['status']=='paid': return {'ok':True,'status':'paid'}
        t=now(); c.execute('UPDATE payment_orders SET status=?,updated_at=? WHERE id=?',(status,t,order_id))
        if status=='paid':
            c.execute('CREATE TABLE IF NOT EXISTS coin_wallets(user_id TEXT PRIMARY KEY,balance INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS coin_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,amount INTEGER NOT NULL,kind TEXT NOT NULL,reference TEXT,created_at TEXT NOT NULL)')
            wallet=c.execute('SELECT balance FROM coin_wallets WHERE user_id=?',(row['user_id'],)).fetchone(); balance=int(wallet[0]) if wallet else 0
            c.execute('INSERT INTO coin_wallets(user_id,balance,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,updated_at=excluded.updated_at',(row['user_id'],balance+int(row['coins']),t))
            c.execute('INSERT INTO coin_transactions(user_id,amount,kind,reference,created_at) VALUES(?,?,?,?,?)',(row['user_id'],int(row['coins']),'coin_purchase',order_id,t))
    return {'ok':True,'status':status}
