from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Header

from main import current_user, db
from content_topics import infer_topics

router = APIRouter(prefix="/api", tags=["smart-search"])
_TAG_RE = re.compile(r"#[\w\u00c0-\uffff]+", re.UNICODE)
_STOP = {"the", "and", "for", "with", "from", "this", "that", "how", "what", "show", "best", "about", "video", "videos"}
_TOPICS = ("technology", "gaming", "education", "business", "fitness", "food", "travel", "music", "comedy", "sports")

def _age_hours(value: str | None) -> float:
    if not value: return 999.0
    try:
        text = value.replace(" ", "T")
        if not text.endswith("Z"): text += "Z"
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    except (TypeError, ValueError): return 999.0

def _text(row: dict) -> str:
    return " ".join(str(row.get(k) or "") for k in ("caption", "title", "description", "username", "display_name"))

def _tags(text: str) -> list[str]: return [x.lower() for x in _TAG_RE.findall(text)]

def _words(value: str) -> list[str]:
    return [w for w in re.findall(r"[\w\u00c0-\uffff]+", value.lower()) if len(w) > 1 and w not in _STOP]

def _score(video: dict, query: str, query_topics: list[str], profile: dict[str, float], followed: bool) -> float:
    q = query.lower().strip(); clean = q.lstrip("#@").strip()
    username = str(video.get("username") or "").lower(); display = str(video.get("display_name") or "").lower(); caption = str(video.get("caption") or "").lower()
    score = 0.0
    if username == clean: score += 150
    elif username.startswith(clean): score += 105
    elif clean and clean in username: score += 65
    if display == clean: score += 115
    elif clean and clean in display: score += 50
    if caption == q: score += 105
    if q in caption: score += 70
    for word in _words(clean):
        if word in caption: score += 20
        if f"#{word}" in caption: score += 32
        if word in username or word in display: score += 10
    if q.startswith("#") and f"#{clean}" in caption: score += 100
    topics = infer_topics(_text(video))
    score += sum(profile.get(t, 0.0) * 7.0 for t in topics)
    score += sum(38.0 for t in topics if t in query_topics)
    if followed: score += 22
    score += min(25.0, math.log1p(float(video.get("likes") or 0)) * 3.0)
    score += min(18.0, math.log1p(float(video.get("views") or 0)) * 1.8)
    score += max(0.0, 18.0 - _age_hours(video.get("created_at")) * 0.18)
    return score

def _discovery(rows: list[dict]) -> tuple[list[str], list[str], list[str]]:
    tags: dict[str, float] = {}; topics: dict[str, float] = {}; creators: dict[str, float] = {}
    for row in rows:
        engagement = math.log1p(float(row.get("likes") or 0) + float(row.get("views") or 0) * 0.25)
        weight = engagement * max(0.2, math.exp(-_age_hours(row.get("created_at")) / 72.0))
        for tag in _tags(str(row.get("caption") or "")): tags[tag] = tags.get(tag, 0.0) + weight
        for topic in infer_topics(_text(row)): topics[topic] = topics.get(topic, 0.0) + weight
        username = str(row.get("username") or "").strip()
        if username: creators[username] = creators.get(username, 0.0) + weight
    tags_sorted = [x for x, _ in sorted(tags.items(), key=lambda x: (-x[1], x[0]))]
    topic_sorted = [x.title() for x, _ in sorted(topics.items(), key=lambda x: (-x[1], x[0]))]
    queries = list(dict.fromkeys(tags_sorted[:8] + topic_sorted[:8]))[:12]
    return queries, tags_sorted[:20], [x for x, _ in sorted(creators.items(), key=lambda x: (-x[1], x[0]))[:8]]

def _suggestions(query: str, rows: list[dict]) -> list[str]:
    q = query.lower().lstrip("#@").strip(); values: list[tuple[float, str]] = []
    for row in rows:
        username = str(row.get("username") or "").strip(); display = str(row.get("display_name") or "").strip()
        if q and q in username.lower(): values.append((5.0 if username.lower().startswith(q) else 3.0, f"@{username}"))
        if q and q in display.lower(): values.append((4.0 if display.lower().startswith(q) else 2.5, display))
        for tag in _tags(str(row.get("caption") or "")):
            if q and q in tag.lstrip("#"): values.append((3.0, tag))
    for topic in _TOPICS:
        if q and q in topic: values.append((4.0, topic.title()))
    seen: set[str] = set(); out: list[str] = []
    for _, value in sorted(values, key=lambda x: (-x[0], x[1].lower())):
        if value.lower() not in seen: seen.add(value.lower()); out.append(value)
        if len(out) >= 8: break
    return out

@router.get("/smart-search")
def smart_search(q: str = "", limit: int = 30, authorization: str | None = Header(default=None)):
    query = q.strip(); limit = max(1, min(limit, 50)); uid = current_user(authorization)
    with db() as c:
        rows = c.execute("""SELECT v.*, u.username, u.display_name,
            CASE WHEN f.follower_id IS NULL THEN 0 ELSE 1 END AS followed_creator
            FROM videos v JOIN users u ON u.id=v.user_id LEFT JOIN follows f ON f.following_id=v.user_id AND f.follower_id=?
            WHERE v.status='ready' ORDER BY v.created_at DESC LIMIT 500""", (uid or "",)).fetchall()
        history = c.execute("""SELECT v.*, CASE WHEN e.action IN ('watch','complete','like','comment','share','save') THEN 1 ELSE -1 END signal
            FROM events e JOIN videos v ON v.id=e.video_id WHERE e.user_id=? AND e.created_at >= datetime('now','-30 days')
            ORDER BY e.created_at DESC LIMIT 300""", (uid,)).fetchall() if uid else []
    data = [dict(r) for r in rows]; trending_queries, trending_hashtags, trending_creators = _discovery(data)
    if not query:
        return {"query":"", "items":[], "suggestions":trending_queries[:8], "topics":[], "trending_topics":trending_queries[:8], "trending_hashtags":trending_hashtags[:12], "trending_creators":trending_creators, "personalized":bool(uid)}
    profile: dict[str, float] = {}
    for row in history:
        for topic in infer_topics(_text(dict(row))): profile[topic] = profile.get(topic, 0.0) + float(row["signal"] or 0)
    query_topics = infer_topics(query, limit=4); ranked = []
    for video in data:
        followed = bool(video.pop("followed_creator", 0)); ranked.append((_score(video, query, query_topics, profile, followed), video))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return {"query":query, "items":[v for _, v in ranked[:limit]], "suggestions":_suggestions(query, data), "topics":query_topics,
            "trending_topics":trending_queries[:8], "trending_hashtags":trending_hashtags[:12], "trending_creators":trending_creators, "personalized":bool(uid)}
