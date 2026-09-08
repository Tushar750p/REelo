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
COIN_PACKAGES = {
    "starter": {"coins": 100, "label": "100 Coins"},
    "creator": {"coins": 550, "label": "550 Coins"},
    "popular": {"coins": 1200, "label": "1,200 Coins"},
    "mega": {"coins": 5000, "label": "5,000 Coins"},
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
    c.execute("CREATE TABLE IF NOT EXISTS live_creator_earnings(id INTEGER PRIMARY KEY AUTOINCREMENT, room_id TEXT NOT NULL, creator_id TEXT NOT NULL, sender_id TEXT NOT NULL, gift_id TEXT NOT NULL, gross_coins INTEGER NOT NULL, creator_coins INTEGER NOT NULL, platform_coins INTEGER NOT NULL, created_at TEXT NOT NULL)")


def now():
    return datetime.now(timezone.utc).isoformat()


class GiftRequest(BaseModel):
    gift_id: str
    quantity: int = 1


class TopupRequest(BaseModel):
    package_id: str


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
        creator_share = (cost * 70) // 100
        platform_share = cost - creator_share
        t = now()
        c.execute("INSERT INTO coin_wallets(user_id,balance,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,updated_at=excluded.updated_at", (uid,balance-cost,t))
        c.execute("INSERT INTO coin_transactions(user_id,amount,kind,reference,created_at) VALUES(?,?,?,?,?)", (uid,-cost,"gift_sent",room_id,t))
        c.execute("INSERT INTO live_gifts(room_id,sender_id,receiver_id,gift_id,coins,created_at) VALUES(?,?,?,?,?,?)", (room_id,uid,receiver,gift_id,cost,t))
        c.execute("INSERT INTO live_creator_earnings(room_id,creator_id,sender_id,gift_id,gross_coins,creator_coins,platform_coins,created_at) VALUES(?,?,?,?,?,?,?,?)", (room_id,receiver,uid,gift_id,cost,creator_share,platform_share,t))
        return {"ok": True, "gift": {"id": gift_id, **gift, "quantity": qty}, "spent": cost, "balance": balance-cost}


@router.get("/{room_id}/gift-feed")
def gift_feed(room_id: str, authorization: str | None = Header(default=None)):
    uid_from(authorization)
    with db() as c:
        ensure_tables(c)
        rows = c.execute("SELECT sender_id,receiver_id,gift_id,coins,created_at FROM live_gifts WHERE room_id=? ORDER BY id DESC LIMIT 30", (room_id,)).fetchall()
    return {"items": [dict(r) | {"gift": GIFTS.get(r["gift_id"], {})} for r in rows]}


@router.get("/{room_id}/creator-earnings")
def creator_earnings(room_id: str, authorization: str | None = Header(default=None)):
    uid = uid_from(authorization)
    with db() as c:
        ensure_tables(c)
        room = c.execute("SELECT user_id FROM live_rooms WHERE id=?", (room_id,)).fetchone()
        if not room or str(room[0]) != uid:
            raise HTTPException(403, "Only the LIVE creator can view earnings")
        total = c.execute("SELECT COALESCE(SUM(gross_coins),0),COALESCE(SUM(creator_coins),0),COALESCE(SUM(platform_coins),0),COUNT(*) FROM live_creator_earnings WHERE room_id=?", (room_id,)).fetchone()
        rows = c.execute("SELECT gift_id,gross_coins,creator_coins,created_at FROM live_creator_earnings WHERE room_id=? ORDER BY id DESC LIMIT 100", (room_id,)).fetchall()
    return {"room_id": room_id, "gross_coins": int(total[0]), "creator_coins": int(total[1]), "platform_coins": int(total[2]), "gift_count": int(total[3]), "items": [dict(r) | {"gift": GIFTS.get(r["gift_id"], {})} for r in rows], "note": "Creator share is virtual coin accounting; payout requires a verified production payment system."}
