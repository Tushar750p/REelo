"""One-way SQLite -> PostgreSQL migration utility.

The source SQLite file is never modified. Use --dry-run first, then run the
migration against an empty/staging PostgreSQL database before production.
"""
import argparse
import sqlite3
from pathlib import Path

from database_config import database_backend
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


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_schema(conn, table: str):
    return conn.execute(f"PRAGMA table_info({quote(table)})").fetchall()


def migrate(source: Path, dry_run: bool = False):
    if database_backend() != "postgresql":
        raise SystemExit("Set REELO_DATABASE_URL to a PostgreSQL DSN first.")
    if not source.exists():
        raise SystemExit(f"SQLite source not found: {source}")

    src = sqlite3.connect(source)
    src.row_factory = sqlite3.Row
    tables = [r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    print(f"Found {len(tables)} tables: {', '.join(tables)}")

    if dry_run:
        for table in tables:
            columns = table_schema(src, table)
            count = src.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()[0]
            print(f"  {table}: {len(columns)} columns, {count} rows")
        src.close()
        return

    try:
        with connection() as dst:
            for table in tables:
                cols = table_schema(src, table)
                names = [c[1] for c in cols]
                definitions = []
                for c in cols:
                    name, typ, notnull, default, pk = c[1], pg_type(c[2]), c[3], c[4], c[5]
                    definition = f"{quote(name)} {typ}"
                    if notnull:
                        definition += " NOT NULL"
                    if default is not None and str(default).upper() in {"CURRENT_TIMESTAMP", "CURRENT_DATE"}:
                        definition += f" DEFAULT {default}"
                    definitions.append(definition)
                pk_cols = [c[1] for c in cols if c[5]]
                if pk_cols:
                    definitions.append("PRIMARY KEY (" + ", ".join(quote(n) for n in pk_cols) + ")")

                dst.execute(f"CREATE TABLE IF NOT EXISTS {quote(table)} ({', '.join(definitions)})")
                qcols = ",".join(quote(n) for n in names)
                placeholders = ",".join(["%s"] * len(names))
                rows = src.execute(f"SELECT * FROM {quote(table)}").fetchall()
                for row in rows:
                    dst.execute(
                        f"INSERT INTO {quote(table)} ({qcols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                        tuple(row[n] for n in names),
                    )
                print(f"Migrated {table}: {len(rows)} rows")
    finally:
        src.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate REelo SQLite data to PostgreSQL")
    parser.add_argument("--source", default="reelo.db", help="SQLite database path")
    parser.add_argument("--dry-run", action="store_true", help="Inspect tables/row counts without writing")
    args = parser.parse_args()
    migrate(Path(args.source), dry_run=args.dry_run)
