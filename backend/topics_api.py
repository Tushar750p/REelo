from fastapi import APIRouter
from main import db
from content_topics import TOPIC_KEYWORDS, infer_topics

router = APIRouter(prefix="/api/topics", tags=["topics"])

@router.get("")
def topics(limit: int = 20):
    limit = max(1, min(limit, 50))
    with db() as c:
        rows = c.execute("SELECT v.*,u.username,u.display_name FROM videos v JOIN users u ON u.id=v.user_id WHERE v.status='ready' ORDER BY v.created_at DESC LIMIT 300").fetchall()
    counts = {k: 0 for k in TOPIC_KEYWORDS}
    samples = {k: None for k in TOPIC_KEYWORDS}
    for row in rows:
        video = dict(row)
        for topic in infer_topics(video.get('caption', ''), limit=3):
            counts[topic] += 1
            if samples[topic] is None:
                samples[topic] = video
    ranked = sorted(counts, key=lambda x: (-counts[x], x))[:limit]
    return {"items": [{"topic": t, "videos": counts[t], "sample": samples[t]} for t in ranked]}

@router.get("/{topic}")
def topic_videos(topic: str, limit: int = 50):
    key = topic.strip().lower().replace('-', '_')
    if key not in TOPIC_KEYWORDS:
        return {"topic": key, "items": []}
    limit = max(1, min(limit, 50))
    with db() as c:
        rows = c.execute("SELECT v.*,u.username,u.display_name FROM videos v JOIN users u ON u.id=v.user_id WHERE v.status='ready' ORDER BY v.created_at DESC LIMIT 300").fetchall()
    items = []
    for row in rows:
        video = dict(row)
        if key in infer_topics(video.get('caption', ''), limit=3):
            items.append(video)
        if len(items) >= limit:
            break
    return {"topic": key, "items": items, "limit": limit}
