from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from main import app, db, current_user
from moderation import moderate_text
from reports import create_report, ensure_reports_table

router = APIRouter(prefix="/api/moderation", tags=["moderation"])

class ReportRequest(BaseModel):
    target_type: str
    target_id: str
    reason: str
    details: str = ""

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

app.include_router(router)
