"""Backend-neutral DB gateway for REelo's core API.

SQLite remains the default. PostgreSQL uses a bounded psycopg connection pool
with lazy startup, connection health checks, and configurable timeouts.
"""
import os
import re
import sqlite3
from pathlib import Path

_PG_POOL = None


class _PGRow(dict):
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
        return None if row is None else _PGRow(row, self._columns)

    def fetchall(self):
        return [_PGRow(row, self._columns) for row in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class _PGConnection:
    """Compatibility wrapper that borrows a pooled connection per context."""

    def __init__(self, pool):
        self.pool = pool
        self.conn = None
        self._context = None

    @staticmethod
    def _sql(sql: str) -> str:
        sql = sql.replace("?", "%s")
        sql = re.sub(r"\bMAX\s*\(([^(),]+),\s*([^()]+)\)", r"GREATEST(\1, \2)", sql, flags=re.IGNORECASE)
        match = re.search(r"PRAGMA\s+table_info\s*\(\s*([\"']?)([A-Za-z0-9_]+)\1\s*\)", sql, flags=re.IGNORECASE)
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
                f"WHERE table_schema=current_schema() AND table_name='{table}' ORDER BY ordinal_position"
            )
        return re.sub(r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", r"ALTER TABLE \1 ADD COLUMN IF NOT EXISTS \2", sql, flags=re.IGNORECASE)

    def execute(self, sql, params=()):
        if self.conn is None:
            raise RuntimeError("Database connection is not acquired; use 'with db() as conn'.")
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params or ()))
        return _PGResult(cur)

    def executescript(self, sql):
        for statement in re.split(r";\s*", sql):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def __enter__(self):
        self._context = self.pool.connection(timeout=float(os.getenv("REELO_DB_POOL_TIMEOUT", "5")))
        self.conn = self._context.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            return self._context.__exit__(exc_type, exc, tb)
        finally:
            self.conn = None
            self._context = None


def using_postgres() -> bool:
    url = os.getenv("REELO_DATABASE_URL", "").strip().lower()
    return url.startswith(("postgres://", "postgresql://"))


def _get_postgres_pool():
    global _PG_POOL
    if _PG_POOL is not None and not _PG_POOL.closed:
        return _PG_POOL
    from psycopg_pool import ConnectionPool

    connect_timeout = int(os.getenv("REELO_DB_CONNECT_TIMEOUT", "5"))
    min_size = int(os.getenv("REELO_DB_POOL_MIN", "1"))
    max_size = int(os.getenv("REELO_DB_POOL_MAX", "10"))
    pool_timeout = float(os.getenv("REELO_DB_POOL_TIMEOUT", "5"))
    if min_size < 0 or max_size < max(1, min_size):
        raise RuntimeError("Invalid REELO_DB_POOL_MIN/REELO_DB_POOL_MAX configuration")

    _PG_POOL = ConnectionPool(
        conninfo=os.environ["REELO_DATABASE_URL"],
        min_size=min_size,
        max_size=max_size,
        open=False,
        kwargs={"connect_timeout": connect_timeout},
        timeout=pool_timeout,
        check=ConnectionPool.check_connection,
        name="reelo-api",
    )
    _PG_POOL.open()
    return _PG_POOL


def close_postgres_pool() -> None:
    global _PG_POOL
    if _PG_POOL is not None:
        _PG_POOL.close()
        _PG_POOL = None


def postgres_pool_stats() -> dict:
    if _PG_POOL is None or _PG_POOL.closed:
        return {"enabled": False}
    return {"enabled": True, **_PG_POOL.get_stats()}


def db():
    if using_postgres():
        return _PGConnection(_get_postgres_pool())
    db_path = Path(__file__).parent / "reelo.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
