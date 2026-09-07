from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from main import app, db, current_user
from reports import ensure_reports_table

router = APIRouter(prefix="/api/admin/moderation", tags=["admin-moderation"])

VALID_STATUSES = {"open", "resolved", "dismissed"}


def require_admin(authorization: str | None):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    import os
    allowed = {x.strip() for x in os.getenv("REELO_ADMIN_USER_IDS", "").split(",") if x.strip()}
    if uid not in allowed:
        raise HTTPException(403, "Admin access required")
    return uid


class StatusRequest(BaseModel):
    status: str


@router.get("/reports")
def list_reports(status: str = "open", limit: int = 100, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    status = status.strip().lower()
    if status not in VALID_STATUSES | {"all"}:
        raise HTTPException(400, "Invalid report status")
    limit = max(1, min(limit, 200))
    with db() as c:
        ensure_reports_table(c)
        where = "" if status == "all" else "WHERE status=?"
        params = () if status == "all" else (status,)
        rows = c.execute(f"SELECT id,reporter_id,target_type,target_id,reason,details,status,created_at FROM reports {where} ORDER BY created_at DESC LIMIT ?", (*params, limit)).fetchall()
        counts = {row[0]: int(row[1] or 0) for row in c.execute("SELECT status,COUNT(*) FROM reports GROUP BY status").fetchall()}
        total = sum(counts.values())
    return {"items": [dict(r) for r in rows], "stats": {"open": counts.get("open", 0), "resolved": counts.get("resolved", 0), "dismissed": counts.get("dismissed", 0), "total": total}}


@router.post("/reports/{report_id}/status")
def update_report_status(report_id: str, req: StatusRequest, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    status = req.status.strip().lower()
    if status not in VALID_STATUSES:
        raise HTTPException(400, "Invalid report status")
    with db() as c:
        ensure_reports_table(c)
        row = c.execute("SELECT id FROM reports WHERE id=?", (report_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Report not found")
        c.execute("UPDATE reports SET status=? WHERE id=?", (status, report_id))
    return {"ok": True, "report_id": report_id, "status": status}


app.include_router(router)
