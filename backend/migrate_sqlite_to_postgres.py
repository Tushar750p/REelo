"""One-way SQLite -> PostgreSQL migration utility.

Usage:
  REELO_DATABASE_URL='postgresql://...' python migrate_sqlite_to_postgres.py

The source SQLite file is never modified. The utility creates compatible
PostgreSQL tables from SQLite's declared schema and copies all rows. Review
custom SQL/indexes after a dry run before switching production traffic.
"""
import argparse
import re
import sqlite3
from pathlib import Path

from database_config import database_backend, database_url
from postgres_adapter import connection


TYPE_MAP = {
    "INTEGER": "BIGINT",
    "INT": "BIGINT",
    "REAL": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION",
    "BLOB": "BYTEA",
}


def pg_type(sql_type: str) -> str:
    base = (sql_type or "TEXT").upper().split("(", 1)[0].strip()
    return TYPE_MAP.get(base, "TEXT" if base in {"TEXT", "CLOB", "VARCHAR"} else base or "TEXT")


def table_schema(conn, table: str):
    return conn.execute(f'PRAGMA table_info("{table}")').fetchall()


def migrate(source: Path, dry_run: bool = False):
    if database_backend() != "postgresql":
        raise SystemExit("Set REELO_DATABASE_URL to a PostgreSQL DSN first.")
    if not source.exists():
        raise SystemExit(f"SQLite source not found: {source}")

    src = sqlite3.connect(source)
    src.row_factory = sqlite3.Row
    tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    print(f"Found {len(tables)} tables: {', '.join(tables)}")
    if dry_run:
        for table in tables:
            print(f"  {table}: {len(table_schema(src, table))} columns, {src.execute(f' SELECT COUNT(*) FROM \"{table}\"').fetchone()[0]} rows")
        return

    with connection() as dst:
        for table in tables:
            cols = table_schema(src, table)
            names = [c[1] for c in cols]
            quoted_table = '"' + table.replace('"', '""') + '"'
            definitions = []
            for c in cols:
                name, typ, notnull, default, pk = c[1], pg_type(c[2]), c[3], c[4], c[5]
                qname = '"' + name.replace('"', '""') + '"'
                definition = f"{qname} {typ}"
                if pk and typ.startswith("BIGINT"):
                    definition = f"{qname} {typ}"
                if notnull:
                    definition += " NOT NULL"
                if default is not None and str(default).upper() in {"CURRENT_TIMESTAMP", "CURRENT_DATE"}:
                    definition += f" DEFAULT {default}"
                definitions.append(definition)
            pk_cols = [c[1] for c in cols if c[5]]
            if pk_cols:
                definitions.append("PRIMARY KEY (" + ", ".join('"' + n.replace('"', '""') + '"' for n in pk_cols) + ")")
            dst.execute(f"CREATE TABLE IF NOT EXISTS {quoted_table} ({', '.join(definitions)})")

            placeholders = ",".join(["%s"] * len(names))
            qcols = ",".join('"' + n.replace('"', '""') + '"' for n in names)
            rows = src.execute(f'SELECT * FROM {quoted_table}').fetchall()
            for row in rows:
                dst.execute(f"INSERT INTO {quoted_table} ({qcols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING", tuple(row[n] for n in names))
            print(f"Migrated {table}: {len(rows)} rows")
    src.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="reelo.db", help="SQLite database path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    migrate(Path(args.source), dry_run=args.dry_run)
