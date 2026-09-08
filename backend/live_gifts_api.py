from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from main import db, current_user

router = APIRouter(prefix="/api/live", tags=["live-gifts"])

GIFTS = {
    "rose": {"name": "Rose", "coins": 1, "emoji": "🌹"},
    "heart": {"name": "Heart", "coins": 10, "emoji": "❤️"},
    "fire": {"name": "Fire", "coins": 50, "emoji": "🔥"},
    "diamond": {"name": "Diamond", "coins": 100, "emoji": "💎"},
    "crown": {"name": "Crown", "coins": 500, "emoji": "👑"},
}


def uid_from(auth):
    uid = current_user(auth)
    if not uid:
        raise HTTPException(401, "Login required")
    return str(uid)


def ensure_tables(c):
    c.execute("CREATE TABLE IF NOT EXISTS coin_wallets(user_id TEXT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS live_gifts(id INTEGER PRIMARY KEY AUTOINCREMENT, room_id TEXT NOT NULL, sender_id TEXT NOT NULL, receiver_id TEXT NOT NULL, gift_id TEXT NOT NULL, coins INTEGER NOT NULL, created_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS coin_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, amount INTEGER NOT NULL, kind TEXT NOT NULL, reference TEXT, created_at TEXT NOT NULL)")


def now():
    return datetime.now(timezone.utc).isoformat()


class GiftRequest(BaseModel):
    gift_id: str
    quantity: int = 1


@router.get("/{room_id}/gifts")
def gift_catalog(room_id: str, authorization: str | None = Header(default=None)):
    uid_from(authorization)
    return {"items": [{"id": k, **v} for k, v in GIFTS.items()]}


@router.get("/{room_id}/wallet")
def wallet(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_tables(c)
        row = c.execute("SELECT balance FROM coin_wallets WHERE user_id=?", (uid,)).fetchone()
        balance = int(row[0]) if row else 0
    return {"balance": balance, "currency": "coins"}


@router.post("/{room_id}/gifts")
def send_gift(room_id: str, data: GiftRequest, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    gift_id = data.gift_id.strip().lower()
    qty = max(1, min(int(data.quantity), 20))
    gift = GIFTS.get(gift_id)
    if not gift:
        raise HTTPException(400, "Invalid gift")
    with db() as c:
        ensure_tables(c)
        room = c.execute("SELECT user_id,status FROM live_rooms WHERE id=?", (room_id,)).fetchone()
        if not room or room[1] != "live":
            raise HTTPException(404, "LIVE room is not active")
        receiver = str(room[0]); cost = gift["coins"] * qty
        if receiver == uid:
            raise HTTPException(400, "You cannot gift yourself")
        row = c.execute("SELECT balance FROM coin_wallets WHERE user_id=?", (uid,)).fetchone()
        balance = int(row[0]) if row else 0
        if balance < cost:
            raise HTTPException(402, "Not enough coins")
        t = now()
        c.execute("INSERT INTO coin_wallets(user_id,balance,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,updated_at=excluded.updated_at", (uid,balance-cost,t))
        c.execute("INSERT INTO coin_transactions(user_id,amount,kind,reference,created_at) VALUES(?,?,?,?,?)", (uid,-cost,"gift_sent",room_id,t))
        c.execute("INSERT INTO live_gifts(room_id,sender_id,receiver_id,gift_id,coins,created_at) VALUES(?,?,?,?,?,?)", (room_id,uid,receiver,gift_id,cost,t))
        return {"ok": True, "gift": {"id": gift_id, **gift, "quantity": qty}, "spent": cost, "balance": balance-cost}


@router.get("/{room_id}/gift-feed")
def gift_feed(room_id: str, authorization: str | None = Header(default=None)):
    uid_from(authorization)
    with db() as c:
        ensure_tables(c)
        rows = c.execute("SELECT sender_id,receiver_id,gift_id,coins,created_at FROM live_gifts WHERE room_id=? ORDER BY id DESC LIMIT 30", (room_id,)).fetchall()
    return {"items": [dict(r) | {"gift": GIFTS.get(r["gift_id"], {})} for r in rows]}
