"""Backend-neutral DB gateway for REelo's core API.

SQLite remains the default. Set REELO_DATABASE_URL to a PostgreSQL DSN to run
core main.py persistence on PostgreSQL. SQL placeholder conversion is provided
for the existing SQLite-style ``?`` parameters.
"""
import os
import re
import sqlite3
from pathlib import Path


class _PGResult:
    def __init__(self, cursor):
        self._cursor = cursor

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
        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params or ()))
        return _PGResult(cur)

    def executescript(self, sql):
        # SQLite schema scripts in REelo are semicolon-delimited and contain
        # only DDL statements, so execute each statement independently.
        for statement in re.split(r";\s*", sql):
            statement = statement.strip()
            if statement:
                self.conn.cursor().execute(statement)

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
