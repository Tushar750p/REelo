from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Header

from main import current_user, db
from content_topics import infer_topics

router = APIRouter(prefix="/api", tags=["smart-search"])

_TAG_RE = re.compile(r"#[\w\u00c0-\uffff]+", re.UNICODE)


def _age_hours(value: str | None) -> float:
    if not value:
        return 999.0
    try:
        text = value.replace(" ", "T")
        if not text.endswith("Z"):
            text += "Z"
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    except (TypeError, ValueError):
        return 999.0


def _text(row: dict) -> str:
    return " ".join(str(row.get(k) or "") for k in ("caption", "title", "description", "username", "display_name"))


def _tags(text: str) -> list[str]:
    return [x.lower() for x in _TAG_RE.findall(text)]


def _score(video: dict, query: str, query_topics: list[str], profile: dict[str, float], followed: bool) -> float:
    raw = _text(video)
    text = raw.lower()
    q = query.lower().strip()
    clean = q.lstrip("#").strip()
    username = str(video.get("username") or "").lower()
    display = str(video.get("display_name") or "").lower()
    caption = str(video.get("caption") or "").lower()
    score = 0.0
    if username == clean:
        score += 140
    elif username.startswith(clean):
        score += 100
    elif clean and clean in username:
        score += 60
    if display == clean:
        score += 110
    elif clean and clean in display:
        score += 45
    if caption == q:
        score += 100
    if q in caption:
        score += 65
    words = [w for w in re.findall(r"[\w\u00c0-\uffff]+", clean) if len(w) > 1]
    for word in words:
        if word in caption:
            score += 18
        if f"#{word}" in caption:
            score += 30
    if q.startswith("#") and f"#{clean}" in caption:
        score += 90
    topics = infer_topics(_text(video))
    score += sum(profile.get(t, 0.0) * 7.0 for t in topics)
    score += sum(35.0 for t in topics if t in query_topics)
    if followed:
        score += 20
    score += min(25.0, math.log1p(float(video.get("likes") or 0)) * 3.0)
    score += min(18.0, math.log1p(float(video.get("views") or 0)) * 1.8)
    score += max(0.0, 18.0 - _age_hours(video.get("created_at")) * 0.18)
    return score


def _suggestions(c, query: str, rows: list[dict]) -> list[str]:
    q = query.lower().lstrip("#").strip()
    values: list[tuple[float, str]] = []
    for row in rows:
        username = str(row.get("username") or "").strip()
        display = str(row.get("display_name") or "").strip()
        for value, weight in ((f"@{username}", 3.0), (display, 2.0)):
            if value and q in value.lower().lstrip("@").strip():
                values.append((weight, value))
        for tag in _tags(str(row.get("caption") or "")):
            if q in tag.lstrip("#"):
                values.append((1.5, tag))
    for topic in ("technology", "gaming", "education", "business", "fitness", "food", "travel", "music", "comedy", "sports"):
        if q in topic:
            values.append((2.5, topic.title()))
    seen = set()
    out = []
    for _, value in sorted(values, key=lambda x: (-x[0], x[1].lower())):
        key = value.lower()
        if key not in seen:
            seen.add(key)
            out.append(value)
        if len(out) >= 8:
            break
    return out


@router.get("/smart-search")
def smart_search(q: str = "", limit: int = 30, authorization: str | None = Header(default=None)):
    query = q.strip()
    limit = max(1, min(limit, 50))
    if not query:
        return {"query": "", "items": [], "suggestions": [], "topics": [], "trending_topics": []}

    uid = current_user(authorization)
    with db() as c:
        rows = c.execute(
            """
            SELECT v.*, u.username, u.display_name,
                   CASE WHEN f.follower_id IS NULL THEN 0 ELSE 1 END AS followed_creator
            FROM videos v JOIN users u ON u.id=v.user_id
            LEFT JOIN follows f ON f.following_id=v.user_id AND f.follower_id=?
            WHERE v.status='ready'
            ORDER BY v.created_at DESC LIMIT 300
            """,
            (uid or "",),
        ).fetchall()
        history = []
        if uid:
            history = c.execute(
                """SELECT v.*,
                   CASE WHEN e.action IN ('watch','complete','like','comment','share','save') THEN 1 ELSE -1 END signal
                   FROM events e JOIN videos v ON v.id=e.video_id
                   WHERE e.user_id=? AND e.created_at >= datetime('now','-30 days')
                   ORDER BY e.created_at DESC LIMIT 300""",
                (uid,),
            ).fetchall()

    data = [dict(r) for r in rows]
    profile: dict[str, float] = {}
    for row in history:
        for topic in infer_topics(_text(dict(row))):
            profile[topic] = profile.get(topic, 0.0) + float(row["signal"] or 0)
    query_topics = infer_topics(query, limit=4)
    ranked = []
    for video in data:
        ranked.append((_score(video, query, query_topics, profile, bool(video.pop("followed_creator", 0))), video))
    ranked.sort(key=lambda x: x[0], reverse=True)
    items = [video for _, video in ranked[:limit]]
    suggestions = _suggestions(None, query, data)
    topic_counts: dict[str, int] = {}
    for video in data:
        for topic in infer_topics(_text(video)):
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
    trending_topics = [t for t, _ in sorted(topic_counts.items(), key=lambda x: (-x[1], x[0]))[:6]]
    return {
        "query": query,
        "items": items,
        "suggestions": suggestions,
        "topics": query_topics,
        "trending_topics": trending_topics,
        "personalized": bool(uid),
    }
