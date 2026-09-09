from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from main import app, db, current_user
from message_requests_api import router as message_requests_router

router = APIRouter(prefix="/api/privacy", tags=["privacy"])

class PrivacyUpdate(BaseModel):
    private_account: bool | None = None
    activity_status: bool | None = None
    message_requests: bool | None = None


def require_user(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS privacy_settings(user_id TEXT PRIMARY KEY,private_account INTEGER DEFAULT 0,activity_status INTEGER DEFAULT 1,message_requests INTEGER DEFAULT 1,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")

@router.get("/settings")
def get_settings(authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        c.execute("INSERT OR IGNORE INTO privacy_settings(user_id) VALUES(?)", (uid,))
        r = c.execute("SELECT private_account,activity_status,message_requests,updated_at FROM privacy_settings WHERE user_id=?", (uid,)).fetchone()
    return {"settings": {"private_account": bool(r[0]), "activity_status": bool(r[1]), "message_requests": bool(r[2]), "updated_at": r[3]}}

@router.patch("/settings")
def update_settings(data: PrivacyUpdate, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_table(c)
        c.execute("INSERT OR IGNORE INTO privacy_settings(user_id) VALUES(?)", (uid,))
        current = c.execute("SELECT private_account,activity_status,message_requests FROM privacy_settings WHERE user_id=?", (uid,)).fetchone()
        values = (
            int(data.private_account if data.private_account is not None else current[0]),
            int(data.activity_status if data.activity_status is not None else current[1]),
            int(data.message_requests if data.message_requests is not None else current[2]),
            uid,
        )
        c.execute("UPDATE privacy_settings SET private_account=?,activity_status=?,message_requests=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", values)
        r = c.execute("SELECT private_account,activity_status,message_requests,updated_at FROM privacy_settings WHERE user_id=?", (uid,)).fetchone()
    return {"settings": {"private_account": bool(r[0]), "activity_status": bool(r[1]), "message_requests": bool(r[2]), "updated_at": r[3]}}

@router.get("/security-summary")
def security_summary(authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS privacy_settings(user_id TEXT PRIMARY KEY,private_account INTEGER DEFAULT 0,activity_status INTEGER DEFAULT 1,message_requests INTEGER DEFAULT 1,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        session_count = 1 if c.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone() else 0
    return {"sessions": session_count, "password": {"configured": True}, "two_factor": {"available": True, "enabled": False}, "session_security": "active"}

# The privacy module is already mounted by backend/app.py; register requests here
# so the new API stays backward-compatible without changing the large app bootstrap file.
app.include_router(message_requests_router)
