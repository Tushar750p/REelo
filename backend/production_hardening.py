import os
import time
from collections import defaultdict, deque
from threading import Lock
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/system", tags=["system"])

_WINDOW = 60
_MAX_REQUESTS = int(os.getenv("REELO_RATE_LIMIT_PER_MINUTE", "120"))
_BUCKETS = defaultdict(deque)
_LOCK = Lock()


def client_key(request: Request):
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def check_rate_limit(request: Request):
    now = time.monotonic()
    key = client_key(request)
    with _LOCK:
        q = _BUCKETS[key]
        while q and now - q[0] > _WINDOW:
            q.popleft()
        if len(q) >= _MAX_REQUESTS:
            return False
        q.append(now)
    return True


@router.get("/health")
def system_health():
    return {"ok": True, "service": "reelo", "timestamp": int(time.time())}


def install_rate_limit(app):
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path in {"/health", "/api/system/health"}:
            return await call_next(request)
        if not check_rate_limit(request):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error":"rate_limited","message":"Too many requests. Please try again shortly."}, status_code=429, headers={"Retry-After":"60"})
        return await call_next(request)
