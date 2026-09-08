"""Apply versioned PostgreSQL migrations in deterministic order.

Usage:
    REELO_DATABASE_URL=postgresql://... python run_migrations.py

Migrations are transactional and recorded in schema_migrations. SQLite is
intentionally rejected so production schema changes cannot be applied to the
wrong database by accident.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def database_url() -> str:
    return os.getenv("REELO_DATABASE_URL", "").strip()


def migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise RuntimeError(f"No migration files found in {MIGRATIONS_DIR}")
    return files


def validate_migration_names(files: list[Path]) -> None:
    seen: set[str] = set()
    for path in files:
        version = path.name.split("_", 1)[0]
        if not version.isdigit():
            raise RuntimeError(f"Invalid migration filename: {path.name}")
        if version in seen:
            raise RuntimeError(f"Duplicate migration version: {version}")
        seen.add(version)


def run() -> None:
    url = database_url()
    if not url.lower().startswith(("postgres://", "postgresql://")):
        raise RuntimeError("REELO_DATABASE_URL must be a PostgreSQL DSN")

    files = migration_files()
    validate_migration_names(files)

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        for path in files:
            version = path.name.split("_", 1)[0]
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (version,),
                )
                if cur.fetchone():
                    print(f"SKIP {path.name}")
                    continue

            sql = path.read_text(encoding="utf-8").strip()
            if not sql:
                raise RuntimeError(f"Migration is empty: {path.name}")

            # Each migration is committed as one unit. A failed migration is
            # rolled back by psycopg's connection context manager.
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                        (version, path.name),
                    )
            print(f"APPLY {path.name}")

    print("PostgreSQL migrations complete")


if __name__ == "__main__":
    run()
