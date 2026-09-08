"""Create a PostgreSQL custom-format backup for REelo.

The database DSN is read only from REELO_DATABASE_URL so credentials are not
stored in scripts or command-line arguments. The resulting archive can be
restored with pg_restore and should be stored outside the application repo.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def database_url() -> str:
    url = os.getenv("REELO_DATABASE_URL", "").strip()
    if not url.lower().startswith(("postgres://", "postgresql://")):
        raise SystemExit("REELO_DATABASE_URL must point to PostgreSQL")
    return url


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a REelo PostgreSQL backup")
    parser.add_argument("output", type=Path, help="Backup file path (.dump recommended)")
    args = parser.parse_args()

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise SystemExit("pg_dump is required but was not found in PATH")

    url = database_url()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing backup: {output}")

    command = [pg_dump, "--format=custom", "--no-owner", "--file", str(output), url]
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        output.unlink(missing_ok=True)
        raise SystemExit(f"pg_dump failed with exit code {exc.returncode}") from exc

    if not output.is_file() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        raise SystemExit("Backup command completed but produced an empty archive")
    print(f"Backup created: {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
