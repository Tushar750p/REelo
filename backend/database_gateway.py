"""Backend-neutral DB gateway for REelo's core API.

SQLite remains the default. Set REELO_DATABASE_URL to a PostgreSQL DSN to run
core main.py persistence on PostgreSQL. SQL placeholder conversion and a small
SQLite-compatibility surface keep the existing feature APIs portable.
"""
import os
import re
import sqlite3
from pathlib import Path


class _PGResult:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return _Row(row)

    def fetchall(self):
        return [_Row(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class _Row(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class _PGConnection:
    def __init__(self, conn):
        self.conn = conn

    @staticmethod
    def _sql(sql: str) -> str:
        # Keep existing SQLite-style parameters working on psycopg.
        sql = sql.replace("?", "%s")
        # SQLite supports MAX(a,b) as a scalar clamp; PostgreSQL calls this
        # GREATEST(a,b). Only rewrite the two-argument scalar form.
        sql = re.sub(r"\bMAX\(([^(),]+),\s*([^()]+)\)", r"GREATEST(\1, \2)", sql, flags=re.IGNORECASE)
        return sql

    def execute(self, sql, params=()):
        sql = sql.strip()
        pragma = re.match(r"^PRAGMA\s+table_info\(([^)]+)\)\s*$", sql, flags=re.IGNORECASE)
        cur = self.conn.cursor()
        if pragma:
            table = pragma.group(1).strip().strip('"').replace('""', '"')
            cur.execute(
                "SELECT ordinal_position - 1, column_name, data_type, "
                "CASE WHEN is_nullable='NO' THEN 1 ELSE 0 END, column_default, "
                "CASE WHEN EXISTS (SELECT 1 FROM pg_constraint pc "
                "JOIN pg_attribute pa ON pa.attrelid=pc.conrelid AND pa.attnum=ANY(pc.conkey) "
                "WHERE pc.contype='p' AND pc.conrelid=c.table_name::regclass "
                "AND pa.attname=c.column_name) THEN 1 ELSE 0 END "
                "FROM information_schema.columns c "
                "WHERE table_schema=current_schema() AND table_name=%s "
                "ORDER BY ordinal_position",
                (table,),
            )
        else:
            cur.execute(self._sql(sql), tuple(params or ()))
        return _PGResult(cur)

    def executescript(self, sql):
        # REelo schema strings are semicolon-delimited DDL statements.
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
        from psycopg.rows import tuple_row
        return _PGConnection(psycopg.connect(os.environ["REELO_DATABASE_URL"], row_factory=tuple_row))
    db_path = Path(__file__).parent / "reelo.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
