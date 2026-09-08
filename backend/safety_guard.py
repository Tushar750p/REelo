from fastapi import Request
from fastapi.responses import JSONResponse
from automated_moderation import moderate_text


def _moderation_value(result, key, default=None):
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def install_safety_guard(app):
    @app.middleware("http")
    async def safety_guard(request: Request, call_next):
        path = request.url.path
        if request.method == "POST" and ("/comments" in path or path == "/api/videos/upload"):
            body = await request.body()
            text = ""
            if "comments" in path:
                try:
                    import json
                    payload = json.loads(body.decode("utf-8"))
                    text = str(payload.get("body", ""))
                except Exception:
                    text = ""
            elif path == "/api/videos/upload":
                # Multipart uploads can contain binary video bytes. Only inspect the
                # textual caption field; actual media scanning requires a media model.
                raw = body.decode("utf-8", errors="ignore")
                marker = 'name="caption"'
                pos = raw.find(marker)
                if pos >= 0:
                    start = raw.find("\r\n\r\n", pos)
                    if start >= 0:
                        start += 4
                        end = raw.find("\r\n--", start)
                        text = raw[start:end if end >= 0 else len(raw)].strip()

            if text:
                result = moderate_text(text)
                action = _moderation_value(result, "action", "allow")
                if action in {"review", "limit"}:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "detail": "Content blocked by safety checks",
                            "safety": {
                                "action": action,
                                "score": _moderation_value(result, "score", 0),
                                "labels": list(_moderation_value(result, "labels", [])),
                            },
                        },
                    )

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}
            request._receive = receive

        return await call_next(request)
