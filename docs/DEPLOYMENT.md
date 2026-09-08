# REelo Deployment Guide

## Production checklist

1. Set a long random `REELO_SECRET` and never commit it.
2. Set `CORS_ORIGINS` to the exact public web origin(s), not `*`.
3. Configure LiveKit credentials and a public `LIVEKIT_URL`.
4. Put HTTPS/TLS in front of the web and API services.
5. Use persistent storage for media and the SQLite database for small deployments.
6. For multi-instance production, configure Redis and move media to object storage/CDN.
7. Configure Persona/KYC and payment-provider credentials before enabling real payouts or purchases.
8. Configure backups for the database and uploaded media.

## Docker Compose

The repository includes a Compose stack containing the API, Redis, LiveKit and Nginx web service.

Required environment values include:

- `REELO_SECRET`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

Optional production values include:

- `CORS_ORIGINS`
- `REELO_REDIS_URL`
- `REELO_OBJECT_STORAGE_BUCKET`
- `REELO_CDN_BASE_URL`
- `REELO_RATE_LIMIT_PER_MINUTE`

## Health checks

- `/health` is the basic API health endpoint.
- `/api/system/health` exposes service timestamp and configured infrastructure capabilities.

## Important architecture note

The current API stores application data in SQLite. This is suitable for development and small deployments, but a larger multi-instance deployment should migrate transactional data to a managed relational database and use shared object storage for media.

Do not treat the local rate limiter as a distributed rate limiter. Configure a shared Redis-backed implementation before horizontally scaling API instances.
