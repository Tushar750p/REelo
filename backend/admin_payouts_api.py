from fastapi import APIRouter, Header, HTTPException
from main import db, current_user
from payouts_api import ensure_payout_tables
from payout_state import normalize_state, can_transition

router = APIRouter(prefix="/api/admin/payouts", tags=["admin-payouts"])


def require_admin(authorization: str | None):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    # Admin IDs are configured explicitly; never infer admin access from a username.
    import os
    allowed = {x.strip() for x in os.getenv("REELO_ADMIN_USER_IDS", "").split(",") if x.strip()}
    if uid not in allowed:
        raise HTTPException(403, "Admin access required")
    return uid


@router.get("")
def list_payouts(limit: int = 100, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    limit = max(1, min(limit, 200))
    with db() as c:
        ensure_payout_tables(c)
        rows = c.execute("SELECT id,user_id,amount_cents,status,method_id,created_at FROM payout_requests ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/{request_id}/status")
def update_status(request_id: str, status: str, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    try:
        target = normalize_state(status)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    with db() as c:
        ensure_payout_tables(c)
        row = c.execute("SELECT status FROM payout_requests WHERE id=?", (request_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Payout request not found")
        current = normalize_state(row[0])
        if not can_transition(current, target):
            raise HTTPException(409, f"Invalid payout transition: {current} -> {target}")
        c.execute("UPDATE payout_requests SET status=? WHERE id=?", (target, request_id))
    return {"ok": True, "request_id": request_id, "status": target}
