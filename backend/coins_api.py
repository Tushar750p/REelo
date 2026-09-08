from datetime import datetime, timezone
import os, hmac, hashlib
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from main import db, current_user

router = APIRouter(prefix="/api/coins", tags=["coins"])
PACKAGES = {
    "starter": {"coins": 100, "label": "100 Coins", "price_paise": 9900},
    "creator": {"coins": 550, "label": "550 Coins", "price_paise": 49900},
    "popular": {"coins": 1200, "label": "1,200 Coins", "price_paise": 99900},
    "mega": {"coins": 5000, "label": "5,000 Coins", "price_paise": 399900},
}
PAYMENT_MODE = os.getenv("REELO_PAYMENT_MODE", "demo").strip().lower()
WEBHOOK_SECRET = os.getenv("REELO_PAYMENT_WEBHOOK_SECRET", "")

def uid(auth):
    value=current_user(auth)
    if not value: raise HTTPException(401,"Login required")
    return str(value)

def now(): return datetime.now(timezone.utc).isoformat()

def tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS coin_wallets(user_id TEXT PRIMARY KEY,balance INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS coin_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,amount INTEGER NOT NULL,kind TEXT NOT NULL,reference TEXT,created_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS coin_payment_orders(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,package_id TEXT NOT NULL,coins INTEGER NOT NULL,amount_paise INTEGER NOT NULL,status TEXT NOT NULL,provider TEXT NOT NULL,created_at TEXT NOT NULL,completed_at TEXT)")

class Topup(BaseModel): package_id: str
class PaymentComplete(BaseModel): order_id: str

@router.get("/packages")
def packages(authorization: str|None=Header(default=None)):
    uid(authorization)
    return {"items":[{"id":k,"coins":v["coins"],"label":v["label"],"price_paise":v["price_paise"]} for k,v in PACKAGES.items()],"currency":"INR","mode":PAYMENT_MODE}

@router.get("/wallet")
def wallet(authorization: str|None=Header(default=None)):
    user=uid(authorization)
    with db() as c:
        tables(c); row=c.execute("SELECT balance FROM coin_wallets WHERE user_id=?",(user,)).fetchone()
    return {"balance":int(row[0]) if row else 0,"currency":"coins"}

@router.post("/topup")
def topup(data:Topup,authorization: str|None=Header(default=None)):
    user=uid(authorization); key=data.package_id.strip().lower(); package=PACKAGES.get(key)
    if not package: raise HTTPException(400,"Invalid coin package")
    if PAYMENT_MODE!="demo": raise HTTPException(409,"Use the payment order flow for production purchases")
    with db() as c:
        tables(c); row=c.execute("SELECT balance FROM coin_wallets WHERE user_id=?",(user,)).fetchone(); old=int(row[0]) if row else 0
        new=old+package["coins"]; t=now()
        c.execute("INSERT INTO coin_wallets(user_id,balance,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,updated_at=excluded.updated_at",(user,new,t))
        c.execute("INSERT INTO coin_transactions(user_id,amount,kind,reference,created_at) VALUES(?,?,?,?,?)",(user,package["coins"],"demo_topup",key,t))
    return {"ok":True,"balance":new,"coins_added":package["coins"],"mode":"demo"}

@router.post("/orders")
def create_order(data:Topup,authorization: str|None=Header(default=None)):
    user=uid(authorization); key=data.package_id.strip().lower(); package=PACKAGES.get(key)
    if not package: raise HTTPException(400,"Invalid coin package")
    import uuid
    order_id=uuid.uuid4().hex
    with db() as c:
        tables(c)
        c.execute("INSERT INTO coin_payment_orders(id,user_id,package_id,coins,amount_paise,status,provider,created_at) VALUES(?,?,?,?,?,?,?,?)",(order_id,user,key,package["coins"],package["price_paise"],"created",PAYMENT_MODE,now()))
    return {"order_id":order_id,"package_id":key,"coins":package["coins"],"amount_paise":package["price_paise"],"currency":"INR","status":"created","provider":PAYMENT_MODE}

@router.post("/orders/{order_id}/complete-demo")
def complete_demo(order_id:str,authorization: str|None=Header(default=None)):
    user=uid(authorization)
    if PAYMENT_MODE!="demo": raise HTTPException(404,"Demo payment endpoint disabled")
    with db() as c:
        tables(c); row=c.execute("SELECT package_id,coins,status FROM coin_payment_orders WHERE id=? AND user_id=?",(order_id,user)).fetchone()
        if not row: raise HTTPException(404,"Payment order not found")
        if row[2]=="paid": return {"ok":True,"status":"paid","coins":row[1]}
        if row[2]!="created": raise HTTPException(409,"Order is not payable")
        wallet=c.execute("SELECT balance FROM coin_wallets WHERE user_id=?",(user,)).fetchone(); old=int(wallet[0]) if wallet else 0; new=old+int(row[1]); t=now()
        c.execute("UPDATE coin_payment_orders SET status='paid',completed_at=? WHERE id=?",(t,order_id))
        c.execute("INSERT INTO coin_wallets(user_id,balance,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,updated_at=excluded.updated_at",(user,new,t))
        c.execute("INSERT INTO coin_transactions(user_id,amount,kind,reference,created_at) VALUES(?,?,?,?,?)",(user,int(row[1]),"payment_topup",order_id,t))
    return {"ok":True,"status":"paid","balance":new,"coins_added":int(row[1])}

@router.post("/webhooks/payment")
def payment_webhook(payload:dict, x_reelo_signature:str|None=Header(default=None)):
    if not WEBHOOK_SECRET: raise HTTPException(503,"Payment webhook is not configured")
    raw=str(payload.get("order_id","")+"."+str(payload.get("status",""))+"."+str(payload.get("provider_reference",""))).encode()
    expected=hmac.new(WEBHOOK_SECRET.encode(),raw,hashlib.sha256).hexdigest()
    if not x_reelo_signature or not hmac.compare_digest(expected,x_reelo_signature): raise HTTPException(401,"Invalid webhook signature")
    if payload.get("status")!="paid": return {"ok":True,"ignored":True}
    order_id=str(payload.get("order_id",""))
    with db() as c:
        tables(c); row=c.execute("SELECT user_id,coins,status FROM coin_payment_orders WHERE id=?",(order_id,)).fetchone()
        if not row: raise HTTPException(404,"Payment order not found")
        if row[2]=="paid": return {"ok":True,"status":"already_paid"}
        user,coins=row[0],int(row[1]); t=now(); w=c.execute("SELECT balance FROM coin_wallets WHERE user_id=?",(user,)).fetchone(); old=int(w[0]) if w else 0
        c.execute("UPDATE coin_payment_orders SET status='paid',completed_at=? WHERE id=?",(t,order_id))
        c.execute("INSERT INTO coin_wallets(user_id,balance,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,updated_at=excluded.updated_at",(user,old+coins,t))
        c.execute("INSERT INTO coin_transactions(user_id,amount,kind,reference,created_at) VALUES(?,?,?,?,?)",(user,coins,"payment_topup",order_id,t))
    return {"ok":True,"status":"paid"}

@router.get("/transactions")
def transactions(authorization: str|None=Header(default=None)):
    user=uid(authorization)
    with db() as c:
        tables(c); rows=c.execute("SELECT amount,kind,reference,created_at FROM coin_transactions WHERE user_id=? ORDER BY id DESC LIMIT 100",(user,)).fetchall()
    return {"items":[dict(r) for r in rows]}
