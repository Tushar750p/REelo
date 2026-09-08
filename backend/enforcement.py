from __future__ import annotations

from datetime import datetime, timezone
import os

from fastapi import HTTPException


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _admin_ids():
    return {x.strip() for x in os.getenv("REELO_ADMIN_USER_IDS", "").split(",") if x.strip()}


def _state(uid):
    # Keep this module independent from trust_safety_api to avoid an import cycle.
    from main import db
    try:
        with db() as c:
            row = c.execute(
                "SELECT action,expires_at,active,reason FROM safety_restrictions WHERE user_id=?",
                (str(uid),),
            ).fetchone()
            if not row:
                return None
            if int(row["active"] or 0) != 1:
                return None
            expires = row["expires_at"]
            if expires:
                try:
                    if expires <= _now_iso():
                        c.execute(
                            "UPDATE safety_restrictions SET active=0,updated_at=? WHERE user_id=?",
                            (_now_iso(), str(uid)),
                        )
                        return None
                except (TypeError, ValueError):
                    pass
            return dict(row)
    except Exception:
        # Safety enforcement must never take the whole API down when an older DB
        # has not yet created the Trust & Safety tables.
        return None


def _policy(action, method, path):
    method = method.upper()
    path = path.split("?", 1)[0]

    # Always preserve access to authentication, safety status and appeals.
    if path in {"/health", "/api/auth/login", "/api/auth/register"}:
        return False
    if path.startswith("/api/trust-safety"):
        return False
    if path.startswith("/api/admin/"):
        return False

    # Monetization holds only affect money-making and withdrawal actions.
    money_paths = (
        "/api/monetization",
        "/api/payouts",
        "/api/coins",
        "/api/payments",
        "/api/live-gifts",
    )
    if action == "monetization_hold":
        return method in {"POST", "PATCH", "PUT", "DELETE"} and path.startswith(money_paths)

    # A normal restriction stops high-impact participation but keeps the feed,
    # profiles and read-only discovery usable.
    restricted_paths = (
        "/api/videos/upload",
        "/api/videos/",          # likes/comments and other video mutations
        "/api/users/",           # follow/block/community mutations
        "/api/messaging/",       # sending/editing/deleting messages
        "/api/stories/",         # creating or mutating stories
        "/api/remix/",
        "/api/editor/",
        "/api/drafts/",
        "/api/live/",            # starting/managing live sessions
        "/api/livekit/",
        "/api/live-guests/",
        "/api/live-moderation/",
        "/api/live-gifts/",
        "/api/creator/",
    )
    if action == "restriction":
        return method in {"POST", "PATCH", "PUT", "DELETE"} and path.startswith(restricted_paths)

    # Suspension blocks authenticated API activity except safety/appeal access.
    if action == "suspend":
        return path.startswith("/api/") and method != "OPTIONS"

    return False


def install_enforcement(app):
    @app.middleware("http")
    async def trust_safety_enforcement(request, call_next):
        authorization = request.headers.get("authorization")
        uid = None
        if authorization:
            try:
                from main import current_user
                uid = current_user(authorization)
            except Exception:
                uid = None

        # Admins are never accidentally trapped by creator/user enforcement.
        if uid and str(uid) not in _admin_ids():
            state = _state(uid)
            if state and _policy(state.get("action", ""), request.method, request.url.path):
                action = state.get("action", "restriction")
                status = 403
                detail = {
                    "error": "account_restricted",
                    "action": action,
                    "message": (
                        "Your account is temporarily restricted from this action."
                        if action == "restriction"
                        else "Account activity is temporarily suspended."
                        if action == "suspend"
                        else "Monetization activity is temporarily on hold."
                    ),
                    "expires_at": state.get("expires_at"),
                    "reason": state.get("reason", ""),
                    "appeal_available": True,
                }
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=status, content=detail)

        return await call_next(request)

    return app
