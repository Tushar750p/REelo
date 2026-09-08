from fastapi import APIRouter, Header, HTTPException
from main import current_user
from production_infra import infrastructure_status

router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure"])

@router.get("/status")
def status(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return {"status": "ok", "components": infrastructure_status()}
