"""Lightweight recommendation scoring for REelo's For You feed.

The scorer is intentionally dependency-free so it can run with SQLite and scale
later to a dedicated ranking service. It combines explicit engagement, watch
behavior, freshness, creator affinity, and a small exploration bonus.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone


def _log(value: float) -> float:
    return math.log1p(max(0.0, float(value or 0)))


def _age_hours(created_at: str | None) -> float:
    if not created_at:
        return 168.0
    try:
        text = created_at.replace(" ", "T")
        if not text.endswith("Z"):
            text += "Z"
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    except (TypeError, ValueError):
        return 168.0


def score_video(video: dict, *, watch_score: float = 0.0,
                liked: bool = False, followed_creator: bool = False,
                seen: bool = False) -> float:
    """Return a deterministic ranking score for a candidate video."""
    engagement = (
        _log(video.get("likes")) * 1.8
        + _log(video.get("comments")) * 1.25
        + _log(video.get("views")) * 0.45
    )
    watch = max(-4.0, min(8.0, float(watch_score or 0)))
    affinity = 3.0 if followed_creator else 0.0
    explicit = 3.5 if liked else 0.0
    freshness = 3.0 * math.exp(-_age_hours(video.get("created_at")) / 72.0)
    exploration = 0.0 if seen else 0.8
    return engagement + watch + affinity + explicit + freshness + exploration


def rank_videos(videos: list[dict], signals: dict[str, dict] | None = None) -> list[dict]:
    """Rank candidate dictionaries and return them without exposing ranking internals."""
    signals = signals or {}
    ranked = []
    for video in videos:
        s = signals.get(str(video.get("id")), {})
        ranked.append((score_video(video, **s), video))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [video for _, video in ranked]
