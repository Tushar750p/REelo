"""Small PostgreSQL runtime adapter used during the REelo migration.

The existing API remains SQLite-backed in this migration phase. Services can
use this boundary incrementally without a risky big-bang database rewrite.
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
    from psycopg.rows import dict_row
    conn = psycopg.connect(os.environ["REELO_DATABASE_URL"], row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(conn, sql: str, params=()):
    """Execute a query using the API's existing SQLite-style ? parameters."""
    return conn.execute(sql.replace("?", "%s"), params)


def healthcheck() -> bool:
    try:
        with connection() as conn:
            execute(conn, "SELECT 1").fetchone()
        return True
    except Exception:
        return False
