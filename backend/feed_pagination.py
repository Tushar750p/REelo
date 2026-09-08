"""Cursor pagination helpers for REelo feeds.

The cursor is opaque to clients and encodes the feed's stable sort tuple:
(created_at, id). Keyset pagination avoids large OFFSET scans while keeping
SQLite/PostgreSQL SQL parameter compatible.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime


def encode_cursor(created_at: str, video_id: str) -> str:
    payload = {"created_at": created_at, "id": video_id}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    if not cursor or len(cursor) > 512:
        raise ValueError("Invalid cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        created_at = payload["created_at"]
        video_id = payload["id"]
        if not isinstance(created_at, str) or not isinstance(video_id, str):
            raise ValueError
        if not video_id or len(video_id) > 128:
            raise ValueError
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return created_at, video_id
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("Invalid cursor") from exc


def cursor_predicate(cursor: str | None) -> tuple[str, tuple[str, str]]:
    """Return a descending keyset predicate and its parameters."""
    if not cursor:
        return "", ()
    created_at, video_id = decode_cursor(cursor)
    return " AND (v.created_at < ? OR (v.created_at = ? AND v.id < ?))", (
        created_at,
        created_at,
        video_id,
    )
