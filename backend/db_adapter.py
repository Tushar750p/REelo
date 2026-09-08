"""Backend-neutral database facade.

The facade provides a small, SQLite-compatible surface for the existing REelo
modules while PostgreSQL migration is being rolled out. PostgreSQL is opt-in
via REELO_DATABASE_URL; SQLite remains the default until all schema-specific
code has been migrated.
"""
import os
import sqlite3
from contextlib import contextmanager


def backend():
    from database_config import database_backend
    return database_backend()


def _sqlite_connection(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _postgres_connection():
    import psycopg
    from database_config import database_url
    return psycopg.connect(database_url())


@contextmanager
def connect(sqlite_path):
    """Yield a DB connection and commit/rollback transaction safely."""
    conn = _postgres_connection() if backend() == "postgresql" else _sqlite_connection(sqlite_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def placeholder(sql):
    """Convert SQLite qmark placeholders to psycopg placeholders."""
    return sql.replace("?", "%s") if backend() == "postgresql" else sql


def rows(cursor):
    """Return rows in a dict-like form across both drivers."""
    if backend() == "sqlite":
        return cursor.fetchall()
    columns = [d.name if hasattr(d, "name") else d[0] for d in cursor.description or []]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
