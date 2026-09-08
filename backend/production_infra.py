"""Production infrastructure helpers for REelo.

Uses Redis for distributed rate limiting when REELO_REDIS_URL is configured;
otherwise keeps the process-local development fallback.
"""
from collections import defaultdict, deque
from threading import Lock
from time import monotonic
import os

WINDOW_SECONDS = max(1, int(os.getenv("REELO_RATE_WINDOW_SECONDS", "60")))
DEFAULT_LIMIT = max(1, int(os.getenv("REELO_RATE_LIMIT", os.getenv("REELO_RATE_LIMIT_PER_MINUTE", "120"))))
_lock = Lock()
_hits = defaultdict(deque)


def _local_rate_limit(key: str, limit: int, window: int) -> tuple[bool, int]:
    now = monotonic()
    with _lock:
        bucket = _hits[key]
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False, max(1, int(window - (now - bucket[0])))
        bucket.append(now)
    return True, 0


def rate_limit(key: str, limit: int = DEFAULT_LIMIT, window: int = WINDOW_SECONDS) -> tuple[bool, int]:
    """Use Redis when available, with a safe local fallback."""
    try:
        from redis_backend import get_redis
        client = get_redis()
        if client is not None:
            bucket = f"reelo:ratelimit:{key}:{int(monotonic() // window)}"
            count = client.incr(bucket)
            if count == 1:
                client.expire(bucket, max(1, window))
            if count > limit:
                return False, max(1, window - int(monotonic() % window))
            return True, 0
    except Exception:
        pass
    return _local_rate_limit(key, limit, window)


def redis_configured() -> bool:
    return bool(os.getenv("REELO_REDIS_URL", "").strip())


def object_storage_configured() -> bool:
    return bool(os.getenv("REELO_OBJECT_STORAGE_BUCKET", "").strip())


def cdn_configured() -> bool:
    return bool(os.getenv("REELO_CDN_BASE_URL", "").strip())


def infrastructure_status() -> dict:
    return {
        "redis": redis_configured(),
        "object_storage": object_storage_configured(),
        "cdn": cdn_configured(),
        "rate_limiter": "redis-distributed" if redis_configured() else "process-local",
    }
