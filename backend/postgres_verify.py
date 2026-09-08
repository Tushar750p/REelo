"""Verify that a PostgreSQL REelo database is reachable and has expected core tables.

This is intentionally read-only. It does not create, alter, or migrate data.
"""
import argparse
import os

from database_gateway import db, using_postgres

EXPECTED_TABLES = {
    "users", "videos", "likes", "follows", "comments", "events", "notifications"
}


def verify():
    if not using_postgres():
        raise SystemExit("REELO_DATABASE_URL must point to PostgreSQL for verification.")
    with db() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
        ).fetchall()
        tables = {row[0] for row in rows}
        missing = sorted(EXPECTED_TABLES - tables)
        if missing:
            raise SystemExit("PostgreSQL is reachable, but core tables are missing: " + ", ".join(missing))
        print(f"PostgreSQL OK: {len(tables)} tables found; all {len(EXPECTED_TABLES)} core tables are present.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify REelo PostgreSQL connectivity and core schema")
    parser.parse_args()
    verify()
