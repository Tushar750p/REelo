"""Database configuration and migration-readiness helpers.

REelo remains SQLite-first for local development. Production can opt into a
PostgreSQL DSN without changing application code yet; this stage deliberately
only validates/configures the target so the eventual migration is safe.
"""
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
    return {
        "backend": backend,
        "configured": backend in {"sqlite", "postgresql"},
        "host": parsed.hostname if parsed and backend == "postgresql" else None,
        "migration_ready": backend == "postgresql",
    }
