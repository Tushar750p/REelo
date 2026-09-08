# REelo Deployment Guide

## Production checklist

1. Set a long random `REELO_SECRET` and never commit it.
2. Set `CORS_ORIGINS` to the exact public web origin(s), not `*`.
3. Configure LiveKit credentials and a public `LIVEKIT_URL`.
4. Put HTTPS/TLS in front of the web and API services.
5. Use SQLite for local development/small single-instance deployments.
6. For multi-instance production, use PostgreSQL for transactional data, shared Redis, and object storage/CDN for media.
7. Configure Persona/KYC and payment-provider credentials before enabling real payouts or purchases.
8. Configure backups for PostgreSQL and uploaded media.

## Database migration

REelo currently keeps the application runtime SQLite-backed while the PostgreSQL migration layer is introduced safely. The repository now includes:

- `backend/database_config.py` — database DSN/backend detection and health metadata.
- `backend/postgres_adapter.py` — explicit PostgreSQL connection boundary.
- `backend/migrate_sqlite_to_postgres.py` — one-way SQLite data migration utility.

Install dependencies, configure `REELO_DATABASE_URL` with a PostgreSQL DSN, then run a dry run first:

```bash
python migrate_sqlite_to_postgres.py --source reelo.db --dry-run
```

After reviewing the table/row report, run the migration:

```bash
python migrate_sqlite_to_postgres.py --source reelo.db
```

The source SQLite database is not modified. The migration utility creates compatible tables and copies rows with conflict-safe inserts. Production traffic should **not** be switched to PostgreSQL until the migrated database has been validated against the full application schema and a backup/rollback plan is confirmed.

## Docker Compose

The repository includes a Compose stack containing the API, Redis, LiveKit and Nginx web service. The API receives `REELO_DATABASE_URL` from the Compose environment and defaults to SQLite for development.

Required environment values include:

- `REELO_SECRET`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

Production database example:

- `REELO_DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/reelo`

Optional production values include:

- `CORS_ORIGINS`
- `REELO_ENV`
- `REELO_REDIS_URL`
- `REELO_OBJECT_STORAGE_BUCKET`
- `REELO_CDN_BASE_URL`
- `REELO_RATE_LIMIT`
- `REELO_RATE_WINDOW_SECONDS`

## Health checks

- `/health` is the basic API health endpoint.
- `/api/system/health` exposes service timestamp and active rate-limiter mode.
- `/api/ops/health` exposes configured Redis, object-storage/CDN capabilities, and database migration readiness.

## Important architecture note

The current application runtime still uses SQLite directly in its legacy database helper. The PostgreSQL adapter and migration utility are therefore an explicit preparation phase, not a claim that all application queries have already been ported to PostgreSQL. The next database phase should replace the direct SQLite helper with a backend-neutral repository/connection layer and then switch production traffic only after validation.

If `REELO_REDIS_URL` is unavailable, the rate limiter safely falls back to a process-local limiter. Do not horizontally scale API instances while relying on that fallback if globally consistent rate limiting is required.
