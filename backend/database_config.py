"""Database configuration and migration-readiness helpers."""
import os
from urllib.parse import urlparse


def database_url() -> str:
    return os.getenv("REELO_DATABASE_URL", "sqlite:///reelo.db").strip()


def database_backend() -> str:
    url = database_url().lower()
    if url.startswith(("postgres://", "postgresql://")):
        return "postgresql"
    if url.startswith("sqlite://"):
        return "sqlite"
    return "unknown"


def database_status() -> dict:
    url = database_url()
    backend = database_backend()
    parsed = urlparse(url) if backend != "unknown" else None
    healthy = None
    if backend == "postgresql":
        try:
            from postgres_adapter import healthcheck
            healthy = healthcheck()
        except Exception:
            healthy = False
    return {
        "backend": backend,
        "configured": backend in {"sqlite", "postgresql"},
        "host": parsed.hostname if parsed and backend == "postgresql" else None,
        "migration_ready": backend == "postgresql",
        "health": healthy,
    }
