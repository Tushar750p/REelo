"""Dependency-free personalized ranking for REelo's For You feed.

Combines engagement quality, watch behavior, creator affinity, freshness,
exploration, and session-level creator diversity.
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
                seen: bool = False, creator_affinity: float = 0.0,
                recent_creator: bool = False) -> float:
    """Return a deterministic ranking score for one candidate."""
    engagement = (
        _log(video.get("likes")) * 1.8
        + _log(video.get("comments")) * 1.25
        + _log(video.get("views")) * 0.45
    )
    watch = max(-5.0, min(10.0, float(watch_score or 0)))
    affinity = (3.5 if followed_creator else 0.0) + max(-2.0, min(5.0, float(creator_affinity or 0)))
    explicit = 3.5 if liked else 0.0
    freshness = 3.2 * math.exp(-_age_hours(video.get("created_at")) / 72.0)
    exploration = 1.1 if not seen else -0.7
    repeat_penalty = -1.8 if recent_creator else 0.0
    return engagement + watch + affinity + explicit + freshness + exploration + repeat_penalty


def rank_videos(videos: list[dict], signals: dict[str, dict] | None = None) -> list[dict]:
    """Rank candidates and diversify adjacent results by creator."""
    signals = signals or {}
    remaining = []
    for video in videos:
        s = signals.get(str(video.get("id")), {})
        remaining.append((score_video(video, **s), video))
    remaining.sort(key=lambda item: item[0], reverse=True)

    result: list[dict] = []
    creator_counts: dict[str, int] = {}
    while remaining:
        best_i, best_value = 0, float("-inf")
        for i, (base_score, video) in enumerate(remaining):
            creator = str(video.get("user_id") or "")
            repeats = creator_counts.get(creator, 0)
            diversity = 1.8 if repeats == 0 else -1.6 * repeats
            value = base_score + diversity
            if value > best_value:
                best_value, best_i = value, i
        _, video = remaining.pop(best_i)
        creator = str(video.get("user_id") or "")
        creator_counts[creator] = creator_counts.get(creator, 0) + 1
        result.append(video)
    return result
