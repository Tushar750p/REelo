from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
import os

from main import app, db, current_user
from moderation import moderate_text
from reports import create_report, ensure_reports_table

router = APIRouter(prefix="/api/moderation", tags=["moderation"])

class ReportRequest(BaseModel):
    target_type: str
    target_id: str
    reason: str
    details: str = ""

class ReportStatusRequest(BaseModel):
    status: str

@router.post("/check")
def check_text(text: str = ""):
    return moderate_text(text)

@router.post("/reports")
def report(req: ReportRequest, authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    if req.target_type not in {"video", "user", "comment"}:
        raise HTTPException(400, "Invalid target type")
    allowed = {"spam", "harassment", "unsafe", "nudity", "copyright", "other"}
    if req.reason not in allowed:
        raise HTTPException(400, "Invalid report reason")
    if not req.target_id.strip():
        raise HTTPException(400, "Target is required")
    with db() as c:
        ensure_reports_table(c)
        existing = c.execute("SELECT 1 FROM reports WHERE reporter_id=? AND target_type=? AND target_id=? AND status='open' LIMIT 1", (uid, req.target_type, req.target_id)).fetchone()
        if existing:
            return {"ok": True, "duplicate": True}
        report_id = create_report(c, uid, req.target_type, req.target_id, req.reason, req.details)
    return {"ok": True, "report_id": report_id}

def require_admin(authorization: str | None):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    allowed = {x.strip() for x in os.getenv("REELO_ADMIN_USER_IDS", "").split(",") if x.strip()}
    if uid not in allowed:
        raise HTTPException(403, "Admin access required")
    return uid

@router.get("/admin/reports")
def list_reports(status: str = "open", limit: int = 100, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    status = status.strip().lower()
    if status not in {"open", "resolved", "all"}:
        raise HTTPException(400, "Invalid report status")
    limit = max(1, min(limit, 200))
    with db() as c:
        ensure_reports_table(c)
        where = "" if status == "all" else " WHERE status=?"
        args = () if status == "all" else (status,)
        rows = c.execute(f"SELECT id,reporter_id,target_type,target_id,reason,details,status,created_at FROM reports{where} ORDER BY created_at DESC LIMIT ?", args + (limit,)).fetchall()
        stats = {
            "open": c.execute("SELECT COUNT(*) FROM reports WHERE status='open'").fetchone()[0],
            "resolved": c.execute("SELECT COUNT(*) FROM reports WHERE status IN ('resolved','dismissed')").fetchone()[0],
            "total": c.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
        }
    return {"items": [dict(r) for r in rows], "stats": stats}

@router.post("/admin/reports/{report_id}/status")
def update_report_status(report_id: str, req: ReportStatusRequest, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    target = req.status.strip().lower()
    if target not in {"resolved", "dismissed"}:
        raise HTTPException(400, "Invalid report status")
    with db() as c:
        ensure_reports_table(c)
        row = c.execute("SELECT status FROM reports WHERE id=?", (report_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Report not found")
        if row[0] != "open":
            raise HTTPException(409, "Report is already closed")
        c.execute("UPDATE reports SET status=? WHERE id=?", (target, report_id))
    return {"ok": True, "report_id": report_id, "status": target}

app.include_router(router)
