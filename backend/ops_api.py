from fastapi import APIRouter
from datetime import datetime, timezone
import os

from production_infra import infrastructure_status
from database_config import database_status

router = APIRouter(prefix="/api/ops", tags=["operations"])


@router.get("/health")
def ops_health():
    infra = infrastructure_status()
    db = database_status()
    return {
        "status": "ok",
        "service": "reelo",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "infrastructure": infra,
        "database": db,
        "environment": os.getenv("REELO_ENV", "development"),
    }
