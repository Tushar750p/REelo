"""Dependency-free ranking for REelo's For You feed.

Balances relevance, behavior, freshness, exploration, negative feedback and
creator diversity without pretending to predict user behavior.
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
                topic_affinity: float = 0.0, recent_creator: bool = False,
                negative_feedback: float = 0.0, recent_negative: bool = False,
                session_creator_count: int = 0, session_topic_match: float = 0.0) -> float:
    """Return a deterministic relevance score from observed signals."""
    engagement = (_log(video.get("likes")) * 1.8
                  + _log(video.get("comments")) * 1.25
                  + _log(video.get("views")) * 0.45)
    watch = max(-6.0, min(12.0, float(watch_score or 0)))
    affinity = (3.5 if followed_creator else 0.0) + max(-2.0, min(5.0, float(creator_affinity or 0)))
    topic = max(-3.0, min(6.0, float(topic_affinity or 0)))
    explicit = 3.5 if liked else 0.0
    freshness = 3.6 * math.exp(-_age_hours(video.get("created_at")) / 72.0)

    # Exploration gives unseen content a controlled boost. It is reduced for
    # users with strong history only when relevance signals are already strong.
    exploration = 2.0 if not seen else -0.45
    if seen and abs(watch) < 0.5 and abs(topic) < 0.5:
        exploration = 0.8

    negative = max(-10.0, min(0.0, float(negative_feedback or 0)))
    if recent_negative:
        negative -= 4.0

    # Session controls reduce repeated creators and reward continuity with the
    # current topic without allowing one creator to dominate the feed.
    creator_repeat = -2.4 * max(0, int(session_creator_count or 0))
    session_topic = max(-2.0, min(3.0, float(session_topic_match or 0)))
    repeat_penalty = -1.4 if recent_creator else 0.0

    return (engagement + watch + affinity + topic + explicit + freshness
            + exploration + negative + creator_repeat + session_topic + repeat_penalty)


def rank_videos(videos: list[dict], signals: dict[str, dict] | None = None,
                session_creator_counts: dict[str, int] | None = None,
                session_topics: dict[str, float] | None = None) -> list[dict]:
    """Rank candidates while balancing relevance, exploration and diversity."""
    signals = signals or {}
    session_creator_counts = session_creator_counts or {}
    session_topics = session_topics or {}

    remaining = []
    for video in videos:
        vid = str(video.get("id"))
        s = dict(signals.get(vid, {}))
        creator = str(video.get("user_id") or "")
        s["session_creator_count"] = session_creator_counts.get(creator, 0)
        topics = video.get("_topics") or []
        s["session_topic_match"] = sum(session_topics.get(str(t), 0.0) for t in topics)
        remaining.append((score_video(video, **s), video))

    remaining.sort(key=lambda item: item[0], reverse=True)
    result: list[dict] = []
    creator_counts: dict[str, int] = dict(session_creator_counts)

    # Greedy re-ranking lets the first few results maximize both relevance and
    # creator diversity. The session state is local to this request.
    while remaining:
        best_i, best_value = 0, float("-inf")
        for i, (base_score, video) in enumerate(remaining):
            creator = str(video.get("user_id") or "")
            repeats = creator_counts.get(creator, 0)
            diversity = 2.2 if repeats == 0 else -2.0 * repeats
            # A small exploration bonus prevents the same high-volume creators
            # from monopolizing adjacent slots.
            exploration = 0.9 if repeats == 0 else 0.0
            value = base_score + diversity + exploration
            if value > best_value:
                best_value, best_i = value, i
        _, video = remaining.pop(best_i)
        creator = str(video.get("user_id") or "")
        creator_counts[creator] = creator_counts.get(creator, 0) + 1
        result.append(video)

    return result
