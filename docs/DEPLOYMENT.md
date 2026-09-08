# REelo Deployment Guide

## Production checklist

1. Set a long random `REELO_SECRET` and never commit it.
2. Set `CORS_ORIGINS` to the exact public web origin(s), not `*`.
3. Configure LiveKit credentials and a public `LIVEKIT_URL`.
4. Put HTTPS/TLS in front of the web and API services.
5. Use persistent storage for media and the SQLite database for small deployments.
6. For multi-instance production, configure shared Redis and move media to object storage/CDN.
7. Configure Persona/KYC and payment-provider credentials before enabling real payouts or purchases.
8. Configure backups for the database and uploaded media.

## Docker Compose

The repository includes a Compose stack containing the API, Redis, LiveKit and Nginx web service. The API is wired to the Compose Redis service through `REELO_REDIS_URL`, so rate limiting can be shared across API instances when they use the same Redis deployment.

Required environment values include:

- `REELO_SECRET`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

Optional production values include:

- `CORS_ORIGINS`
- `REELO_ENV`
- `REELO_REDIS_URL`
- `REELO_OBJECT_STORAGE_BUCKET`
- `REELO_CDN_BASE_URL`
- `REELO_RATE_LIMIT`
- `REELO_RATE_WINDOW_SECONDS`

`REELO_RATE_LIMIT_PER_MINUTE` remains supported as a compatibility fallback for the rate limit value.

## Health checks

- `/health` is the basic API health endpoint.
- `/api/system/health` exposes service timestamp and active rate-limiter mode.
- `/api/ops/health` exposes configured Redis, object-storage and CDN capabilities.

## Important architecture note

The current API stores application data in SQLite. This is suitable for development and small deployments, but a larger multi-instance deployment should migrate transactional data to a managed relational database and use shared object storage for media.

If `REELO_REDIS_URL` is unavailable, the rate limiter safely falls back to a process-local limiter. Do not horizontally scale API instances while relying on that fallback if globally consistent rate limiting is required.
