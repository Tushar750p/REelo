from fastapi import APIRouter
from datetime import datetime, timezone
import os

from production_infra import infrastructure_status

router = APIRouter(prefix="/api/ops", tags=["operations"])


@router.get("/health")
def ops_health():
    return {
        "status": "ok",
        "service": "reelo",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "infrastructure": infrastructure_status(),
        "environment": os.getenv("REELO_ENV", "development"),
    }
