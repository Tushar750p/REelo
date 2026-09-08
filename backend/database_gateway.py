"""Backend-neutral DB gateway for REelo's core API.

SQLite remains the default. PostgreSQL uses a bounded psycopg connection pool
when REELO_DATABASE_URL points to PostgreSQL. The public db() context keeps the
existing SQLite-style API while returning pooled connections safely.
"""
import atexit
import os
import re
import sqlite3
from pathlib import Path
from threading import Lock


class _PGRow(dict):
    """Mapping row that also supports SQLite-style numeric indexing."""

    def __init__(self, values, columns):
        super().__init__(zip(columns, values))
        self._columns = tuple(columns)

    def __getitem__(self, key):
        if isinstance(key, int):
            return dict.__getitem__(self, self._columns[key])
        return dict.__getitem__(self, key)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class _PGResult:
    def __init__(self, cursor):
        self._cursor = cursor
        self._columns = tuple(desc.name for desc in (cursor.description or ()))

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return _PGRow(row, self._columns)

    def fetchall(self):
        return [_PGRow(row, self._columns) for row in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class _PGConnection:
    def __init__(self, pool):
        self._pool = pool
        self._pool_context = None
        self.conn = None

    def _ensure_connection(self):
        if self.conn is None:
            timeout = float(os.getenv("REELO_DB_POOL_TIMEOUT", "5"))
            self._pool_context = self._pool.connection(timeout=timeout)
            self.conn = self._pool_context.__enter__()
        return self.conn

    @staticmethod
    def _sql(sql: str) -> str:
        sql = sql.replace("?", "%s")
        sql = re.sub(
            r"\bMAX\s*\(([^(),]+),\s*([^()]+)\)",
            r"GREATEST(\1, \2)",
            sql,
            flags=re.IGNORECASE,
        )
        match = re.search(
            r"PRAGMA\s+table_info\s*\(\s*([\"']?)([A-Za-z0-9_]+)\1\s*\)",
            sql,
            flags=re.IGNORECASE,
        )
        if match:
            table = match.group(2).replace("'", "''")
            return (
                "SELECT (ordinal_position - 1) AS cid, column_name AS name, "
                "data_type AS type, CASE WHEN is_nullable='NO' THEN 1 ELSE 0 END AS notnull, "
                "column_default AS dflt_value, CASE WHEN EXISTS ("
                "SELECT 1 FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name=tc.constraint_name "
                "AND kcu.table_schema=tc.table_schema AND kcu.table_name=tc.table_name "
                "WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=current_schema() "
                f"AND tc.table_name='{table}' AND kcu.column_name=c.column_name) THEN 1 ELSE 0 END AS pk "
                "FROM information_schema.columns c "
                f"WHERE table_schema=current_schema() AND table_name='{table}' "
                "ORDER BY ordinal_position"
            )
        sql = re.sub(
            r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)",
            r"ALTER TABLE \1 ADD COLUMN IF NOT EXISTS \2",
            sql,
            flags=re.IGNORECASE,
        )
        return sql

    def execute(self, sql, params=()):
        cur = self._ensure_connection().cursor()
        cur.execute(self._sql(sql), tuple(params or ()))
        return _PGResult(cur)

    def executescript(self, sql):
        for statement in re.split(r";\s*", sql):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def __enter__(self):
        self._ensure_connection()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._pool_context is not None:
            try:
                self._pool_context.__exit__(exc_type, exc, tb)
            finally:
                self._pool_context = None
                self.conn = None
        return False


_POOL = None
_POOL_LOCK = Lock()


def using_postgres() -> bool:
    url = os.getenv("REELO_DATABASE_URL", "").strip().lower()
    return url.startswith(("postgres://", "postgresql://"))


def _postgres_pool():
    global _POOL
    if _POOL is not None:
        return _POOL
    with _POOL_LOCK:
        if _POOL is None:
            from psycopg_pool import ConnectionPool

            min_size = max(1, int(os.getenv("REELO_DB_POOL_MIN", "1")))
            max_size = max(min_size, int(os.getenv("REELO_DB_POOL_MAX", "10")))
            connect_timeout = int(os.getenv("REELO_DB_CONNECT_TIMEOUT", "5"))
            _POOL = ConnectionPool(
                conninfo=os.environ["REELO_DATABASE_URL"],
                min_size=min_size,
                max_size=max_size,
                open=False,
                timeout=float(os.getenv("REELO_DB_POOL_TIMEOUT", "5")),
                kwargs={"connect_timeout": connect_timeout},
                check=ConnectionPool.check_connection,
            )
            _POOL.open(wait=False)
    return _POOL


def open_pool(wait=False):
    """Open the PostgreSQL pool explicitly, optionally waiting for min_size."""
    if not using_postgres():
        return False
    pool = _postgres_pool()
    if not pool.closed:
        if wait:
            pool.wait(timeout=float(os.getenv("REELO_DB_CONNECT_TIMEOUT", "5")))
        return True
    raise RuntimeError("PostgreSQL connection pool is closed and cannot be reopened")


def close_pool():
    """Close the PostgreSQL pool and release all idle resources."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is not None:
            _POOL.close()
            _POOL = None


def pool_status() -> dict:
    """Return safe pool metrics without exposing connection credentials."""
    if not using_postgres():
        return {"enabled": False, "backend": "sqlite"}
    pool = _postgres_pool()
    stats = pool.get_stats()
    return {
        "enabled": True,
        "backend": "postgresql",
        "closed": pool.closed,
        "pool_min": pool.min_size,
        "pool_max": pool.max_size,
        "pool_size": stats.get("pool_size", 0),
        "pool_available": stats.get("pool_available", 0),
        "requests_waiting": stats.get("requests_waiting", 0),
    }


atexit.register(close_pool)


def db():
    if using_postgres():
        return _PGConnection(_postgres_pool())
    db_path = Path(__file__).parent / "reelo.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
