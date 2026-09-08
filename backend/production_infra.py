"""Production infrastructure helpers for REelo.

The module is intentionally dependency-free. It provides safe defaults for
cache/rate-limit primitives while allowing Redis to be enabled later through
REELO_REDIS_URL. Local fallback is process-local and should only be used for
single-instance deployments.
"""
from collections import defaultdict, deque
from threading import Lock
from time import monotonic
import os

WINDOW_SECONDS = max(1, int(os.getenv("REELO_RATE_WINDOW_SECONDS", "60")))
DEFAULT_LIMIT = max(1, int(os.getenv("REELO_RATE_LIMIT", "120")))

_lock = Lock()
_hits = defaultdict(deque)


def rate_limit(key: str, limit: int = DEFAULT_LIMIT, window: int = WINDOW_SECONDS) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds) using a sliding-window counter."""
    now = monotonic()
    bucket = _hits[key]
    with _lock:
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry = max(1, int(window - (now - bucket[0])))
            return False, retry
        bucket.append(now)
    return True, 0


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
        "rate_limiter": "process-local",
    }
