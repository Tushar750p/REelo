"""Small dependency-free API hardening layer for REelo."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from starlette.requests import Request
from starlette.responses import JSONResponse

WINDOW_SECONDS = 60
GENERAL_LIMIT = 120
UPLOAD_WINDOW_SECONDS = 600
UPLOAD_LIMIT = 10
MAX_UPLOAD_REQUEST_BYTES = 110 * 1024 * 1024


def install_security(app):
    general_hits: dict[str, deque[float]] = defaultdict(deque)
    upload_hits: dict[str, deque[float]] = defaultdict(deque)

    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def allowed(bucket: dict[str, deque[float]], key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        hits = bucket[key]
        cutoff = now - window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        key = client_key(request)
        if not allowed(general_hits, key, GENERAL_LIMIT, WINDOW_SECONDS):
            return JSONResponse({"detail": "Too many requests. Please try again shortly."}, status_code=429)

        if request.url.path == "/api/videos/upload":
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > MAX_UPLOAD_REQUEST_BYTES:
                        return JSONResponse({"detail": "Upload request is too large."}, status_code=413)
                except ValueError:
                    return JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)
            if not allowed(upload_hits, key, UPLOAD_LIMIT, UPLOAD_WINDOW_SECONDS):
                return JSONResponse({"detail": "Upload rate limit reached. Please try again later."}, status_code=429)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
