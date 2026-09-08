"""Backend-neutral DB gateway for REelo's core API.

SQLite remains the default. Set REELO_DATABASE_URL to a PostgreSQL DSN to run
core persistence on PostgreSQL. Existing feature APIs can keep their SQLite-style
parameter markers and common compatibility SQL while migrating incrementally.
"""
import os
import re
import sqlite3
from pathlib import Path


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
    def __init__(self, conn):
        self.conn = conn

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
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params or ()))
        return _PGResult(cur)

    def executescript(self, sql):
        for statement in re.split(r";\s*", sql):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
        finally:
            self.conn.close()
        return False


def using_postgres() -> bool:
    url = os.getenv("REELO_DATABASE_URL", "").strip().lower()
    return url.startswith(("postgres://", "postgresql://"))


def db():
    if using_postgres():
        import psycopg
        return _PGConnection(psycopg.connect(os.environ["REELO_DATABASE_URL"]))
    db_path = Path(__file__).parent / "reelo.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
