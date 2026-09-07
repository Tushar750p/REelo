"""Lightweight trending score for REelo discovery."""
from __future__ import annotations
import math
from datetime import datetime, timezone


def _age_hours(value: str | None) -> float:
    if not value:
        return 168.0
    try:
        text=value.replace(' ','T')
        if not text.endswith('Z'): text += 'Z'
        dt=datetime.fromisoformat(text.replace('Z','+00:00'))
        return max(0.0,(datetime.now(timezone.utc)-dt).total_seconds()/3600)
    except (TypeError,ValueError):
        return 168.0


def trending_score(video: dict) -> float:
    """Balance recent engagement against age so old viral videos don't dominate."""
    engagement=(
        math.log1p(max(0,int(video.get('views') or 0))) * 0.8
        + math.log1p(max(0,int(video.get('likes') or 0))) * 2.2
        + math.log1p(max(0,int(video.get('comments') or 0))) * 1.6
    )
    age=_age_hours(video.get('created_at'))
    freshness=6.0*math.exp(-age/48.0)
    return engagement+freshness


def rank_trending(videos: list[dict], limit: int=20) -> list[dict]:
    ranked=sorted(videos,key=trending_score,reverse=True)
    return ranked[:max(1,min(limit,50))]
