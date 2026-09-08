"""Optional Redis-backed primitives for multi-instance REelo deployments.

Redis is enabled only when REELO_REDIS_URL is configured. The application can
safely fall back to the existing process-local implementation in development.
"""
import os
from typing import Optional

_client = None


def get_redis():
    global _client
    url = os.getenv("REELO_REDIS_URL", "").strip()
    if not url:
        return None
    if _client is not None:
        return _client
    try:
        import redis
        _client = redis.Redis.from_url(url, decode_responses=True)
        _client.ping()
        return _client
    except Exception:
        _client = None
        return None


def redis_available() -> bool:
    return get_redis() is not None


def set_value(key: str, value: str, ttl: int = 300) -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        client.setex(key, max(1, ttl), value)
        return True
    except Exception:
        return False


def get_value(key: str) -> Optional[str]:
    client = get_redis()
    if client is None:
        return None
    try:
        return client.get(key)
    except Exception:
        return None
