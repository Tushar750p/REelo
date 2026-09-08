from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from main import db, current_user

router = APIRouter(prefix="/api/coins", tags=["coins"])
PACKAGES = {
    "starter": {"coins": 100, "label": "100 Coins"},
    "creator": {"coins": 550, "label": "550 Coins"},
    "popular": {"coins": 1200, "label": "1,200 Coins"},
    "mega": {"coins": 5000, "label": "5,000 Coins"},
}

def uid(auth):
    value = current_user(auth)
    if not value: raise HTTPException(401, "Login required")
    return str(value)

def now(): return datetime.now(timezone.utc).isoformat()

def tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS coin_wallets(user_id TEXT PRIMARY KEY,balance INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS coin_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,amount INTEGER NOT NULL,kind TEXT NOT NULL,reference TEXT,created_at TEXT NOT NULL)")

class Topup(BaseModel): package_id: str

@router.get("/packages")
def packages(authorization: str|None=Header(default=None)):
    uid(authorization)
    return {"items":[{"id":k,**v} for k,v in PACKAGES.items()]}

@router.get("/wallet")
def wallet(authorization: str|None=Header(default=None)):
    user=uid(authorization)
    with db() as c:
        tables(c); row=c.execute("SELECT balance FROM coin_wallets WHERE user_id=?",(user,)).fetchone()
    return {"balance":int(row[0]) if row else 0,"currency":"coins"}

@router.post("/topup")
def topup(data:Topup,authorization: str|None=Header(default=None)):
    user=uid(authorization); package=PACKAGES.get(data.package_id.strip().lower())
    if not package: raise HTTPException(400,"Invalid coin package")
    with db() as c:
        tables(c); row=c.execute("SELECT balance FROM coin_wallets WHERE user_id=?",(user,)).fetchone(); old=int(row[0]) if row else 0
        new=old+package["coins"]; t=now()
        c.execute("INSERT INTO coin_wallets(user_id,balance,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,updated_at=excluded.updated_at",(user,new,t))
        c.execute("INSERT INTO coin_transactions(user_id,amount,kind,reference,created_at) VALUES(?,?,?,?,?)",(user,package["coins"],"demo_topup",data.package_id,t))
    return {"ok":True,"balance":new,"coins_added":package["coins"],"mode":"demo"}

@router.get("/transactions")
def transactions(authorization: str|None=Header(default=None)):
    user=uid(authorization)
    with db() as c:
        tables(c); rows=c.execute("SELECT amount,kind,reference,created_at FROM coin_transactions WHERE user_id=? ORDER BY id DESC LIMIT 100",(user,)).fetchall()
    return {"items":[dict(r) for r in rows]}
