"""Safe PostgreSQL observability helpers for REelo operations."""
from __future__ import annotations

import os


def _threshold_ms() -> float:
    try:
        return max(0.0, float(os.getenv("REELO_SLOW_QUERY_MS", "250")))
    except ValueError:
        return 250.0


def slow_query_threshold_ms() -> float:
    return _threshold_ms()


def pool_alerts(pool_status: dict) -> list[str]:
    """Return operational alert codes without exposing credentials."""
    if not pool_status.get("enabled"):
        return []
    alerts: list[str] = []
    maximum = int(pool_status.get("pool_max", 0) or 0)
    available = int(pool_status.get("pool_available", 0) or 0)
    waiting = int(pool_status.get("requests_waiting", 0) or 0)
    if pool_status.get("closed"):
        alerts.append("postgres_pool_closed")
    if maximum > 0 and available == 0:
        alerts.append("postgres_pool_exhausted")
    if waiting > 0:
        alerts.append("postgres_pool_requests_waiting")
    return alerts


def observability_status(pool_status: dict) -> dict:
    return {
        "slow_query_threshold_ms": slow_query_threshold_ms(),
        "pool_alerts": pool_alerts(pool_status),
    }
