import os
import time
from collections import defaultdict, deque
from threading import Lock
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/system", tags=["system"])
_WINDOW = max(1, int(os.getenv("REELO_RATE_WINDOW_SECONDS", "60")))
_MAX_REQUESTS = max(1, int(os.getenv("REELO_RATE_LIMIT", os.getenv("REELO_RATE_LIMIT_PER_MINUTE", "120"))))
_BUCKETS = defaultdict(deque)
_LOCK = Lock()
_REDIS = None
_REDIS_FAILED = False


def client_key(request: Request):
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _redis_client():
    global _REDIS, _REDIS_FAILED
    url = os.getenv("REELO_REDIS_URL", "").strip()
    if not url or _REDIS_FAILED:
        return None
    if _REDIS is None:
        try:
            import redis
            _REDIS = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
            _REDIS.ping()
        except Exception:
            _REDIS_FAILED = True
            _REDIS = None
    return _REDIS


def check_rate_limit(request: Request):
    key = client_key(request)
    client = _redis_client()
    if client:
        try:
            bucket = f"reelo:rate:{key}"
            now = time.time()
            pipe = client.pipeline()
            pipe.zremrangebyscore(bucket, 0, now - _WINDOW)
            pipe.zcard(bucket)
            count = pipe.execute()[1]
            if count >= _MAX_REQUESTS:
                return False
            member = f"{now:.6f}:{os.urandom(4).hex()}"
            client.zadd(bucket, {member: now})
            client.expire(bucket, _WINDOW + 1)
            return True
        except Exception:
            pass
    now = time.monotonic()
    with _LOCK:
        q = _BUCKETS[key]
        while q and now - q[0] > _WINDOW:q.popleft()
        if len(q) >= _MAX_REQUESTS:return False
        q.append(now)
    return True


@router.get("/health")
def system_health():
    return {"ok": True, "service": "reelo", "timestamp": int(time.time()), "rate_limiter": "redis" if _redis_client() else "process-local"}


def install_rate_limit(app):
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path in {"/health", "/api/system/health"}:return await call_next(request)
        if not check_rate_limit(request):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error":"rate_limited","message":"Too many requests. Please try again shortly."},status_code=429,headers={"Retry-After":str(_WINDOW)})
        return await call_next(request)
