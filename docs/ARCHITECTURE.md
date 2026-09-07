# REelo Architecture

## Product Layers

### Client
Flutter mobile application with a vertical short-video experience.

### API
FastAPI service for authentication, users, videos, social graph, feed, comments, notifications, and admin APIs.

### Data
PostgreSQL for durable relational data and Redis for caching, rate limits, sessions, and feed acceleration.

### Media
Object storage for original/processed videos and HLS segments. FFmpeg handles transcoding, thumbnails, and media normalization.

### AI
Python services for:
- recommendation ranking
- video understanding and metadata extraction
- caption/hashtag generation
- moderation and safety classification
- semantic search

## Initial Directory Layout

```text
reelo/
├── app/                    # Flutter application
├── backend/                # FastAPI service
├── ai/                     # AI/recommendation services
├── infra/                  # Docker and deployment configuration
├── docs/                   # Architecture and product docs
└── .github/                # CI/CD workflows
```

## Design Principles

1. API-first and mobile-first.
2. Media processing is asynchronous.
3. Recommendation signals are event-driven.
4. Safety checks are applied before broad distribution.
5. Secrets never live in source control.
6. Local development should work without paid infrastructure.
