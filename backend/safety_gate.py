import re
from fastapi import HTTPException
from automated_moderation import moderate_text


def _extract_text(body: bytes, content_type: str) -> str:
    if not body:
        return ""
    if "application/json" in content_type:
        try:
            import json
            payload = json.loads(body.decode("utf-8"))
            return str(payload.get("body") or payload.get("message") or "")
        except Exception:
            return ""
    if "multipart/form-data" in content_type:
        match = re.search(rb'name=["\']caption["\']\r?\n\r?\n(.*?)(?:\r?\n--)', body, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).decode("utf-8", errors="ignore").strip()
    return ""


def install_safety_gate(app):
    @app.middleware("http")
    async def moderation_gate(request, call_next):
        path = request.url.path
        if request.method in {"POST", "PUT", "PATCH"} and (
            re.fullmatch(r"/api/videos/[^/]+/comments", path)
            or path == "/api/videos/upload"
        ):
            body = await request.body()
            text = _extract_text(body, request.headers.get("content-type", ""))
            if text:
                result = moderate_text(text)
                if result.get("action") in {"review", "limit"}:
                    raise HTTPException(400, "Content blocked by safety checks")
            request._body = body
        return await call_next(request)

    return app
