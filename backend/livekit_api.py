import os
import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from livekit import api

from main import current_user

router = APIRouter(prefix="/api/livekit", tags=["livekit"])


class TokenRequest(BaseModel):
    room: str
    role: str = "viewer"


def require_user(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def safe_room(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]", "", (value or ""))[:100]
    if not value:
        raise HTTPException(400, "Invalid LIVE room")
    return value


@router.post("/token")
def create_livekit_token(data: TokenRequest, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    room = safe_room(data.room)
    role = data.role.strip().lower()
    if role not in {"host", "viewer", "guest"}:
        raise HTTPException(400, "Invalid LIVE role")

    key = os.getenv("LIVEKIT_API_KEY")
    secret = os.getenv("LIVEKIT_API_SECRET")
    url = os.getenv("LIVEKIT_URL")
    if not key or not secret or not url:
        raise HTTPException(503, "Live streaming service is not configured")

    can_publish = role in {"host", "guest"}
    token = (
        api.AccessToken(key, secret)
        .with_identity(str(uid))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=can_publish,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )
    return {"token": token, "url": url, "room": room, "role": role}
