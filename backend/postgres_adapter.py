"""Small PostgreSQL adapter used by migration/health tooling.

The existing API remains SQLite-backed in this migration phase. This module
provides a safe, explicit PostgreSQL connection boundary for production tools.
"""
from contextlib import contextmanager
import os


def postgres_configured() -> bool:
    url = os.getenv("REELO_DATABASE_URL", "").strip().lower()
    return url.startswith(("postgres://", "postgresql://"))


@contextmanager
def connection():
    if not postgres_configured():
        raise RuntimeError("REELO_DATABASE_URL is not configured for PostgreSQL")
    import psycopg
    conn = psycopg.connect(os.environ["REELO_DATABASE_URL"])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
