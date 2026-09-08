from fastapi import APIRouter, Header, HTTPException

from main import current_user, db
from recommendation_engine import rank_videos
from content_topics import infer_topics

router = APIRouter(prefix="/api")


def _content_text(video: dict) -> str:
    """Collect common text fields without requiring a specific schema."""
    keys = ("title", "caption", "description", "text", "hashtags", "tags")
    values = []
    for key in keys:
        value = video.get(key)
        if isinstance(value, (list, tuple)):
            values.extend(str(x) for x in value)
        elif value:
            values.append(str(value))
    return " ".join(values)


@router.get("/recommendations")
def recommendations(limit: int = 20, offset: int = 0, authorization: str | None = Header(default=None)):
    """Personalized For You candidates using behavior, creator/topic affinity and persistent preferences."""
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")

    limit = max(1, min(limit, 50))
    offset = max(0, min(offset, 5000))
    with db() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS blocked_users(blocker_id TEXT NOT NULL, blocked_id TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(blocker_id,blocked_id))"
        )
        rows = c.execute(
            """
            SELECT v.*, u.username, u.display_name,
                   CASE WHEN l.user_id IS NULL THEN 0 ELSE 1 END AS liked,
                   CASE WHEN f.follower_id IS NULL THEN 0 ELSE 1 END AS followed_creator,
                   COALESCE((
                       SELECT SUM(CASE
                           WHEN e.action IN ('watch','complete') THEN MIN(COALESCE(e.seconds,0), 30.0) / 6.0
                           WHEN e.action IN ('skip','dismiss') THEN -2.5
                           WHEN e.action IN ('like','comment','share','save') THEN 2.0
                           ELSE 0 END)
                       FROM events e WHERE e.user_id=? AND e.video_id=v.id
                   ), 0) AS watch_score,
                   COALESCE((
                       SELECT SUM(CASE
                           WHEN e.action IN ('watch','complete') THEN MIN(COALESCE(e.seconds,0), 30.0) / 30.0
                           WHEN e.action IN ('like','comment','share','save') THEN 1.5
                           WHEN e.action IN ('skip','dismiss') THEN -0.75
                           ELSE 0 END)
                       FROM events e JOIN videos hv ON hv.id=e.video_id
                       WHERE e.user_id=? AND hv.user_id=v.user_id AND hv.id<>v.id
                   ), 0) AS creator_affinity,
                   CASE WHEN EXISTS(
                       SELECT 1 FROM events e2 WHERE e2.user_id=? AND e2.video_id=v.id
                   ) THEN 1 ELSE 0 END AS seen,
                   CASE WHEN EXISTS(
                       SELECT 1 FROM events e3 JOIN videos rv ON rv.id=e3.video_id
                       WHERE e3.user_id=? AND rv.user_id=v.user_id
                         AND e3.created_at >= datetime('now','-24 hours')
                   ) THEN 1 ELSE 0 END AS recent_creator
            FROM videos v
            JOIN users u ON u.id=v.user_id
            LEFT JOIN likes l ON l.video_id=v.id AND l.user_id=?
            LEFT JOIN follows f ON f.following_id=v.user_id AND f.follower_id=?
            WHERE v.status='ready'
              AND v.user_id<>?
              AND NOT EXISTS (SELECT 1 FROM blocked_users b WHERE b.blocker_id=? AND b.blocked_id=v.user_id)
              AND NOT EXISTS (SELECT 1 FROM events ni WHERE ni.user_id=? AND ni.video_id=v.id AND ni.action='not_interested' AND ni.created_at>=datetime('now','-90 days'))
              AND NOT EXISTS (SELECT 1 FROM events mc JOIN videos mv ON mv.id=mc.video_id WHERE mc.user_id=? AND mc.action='mute_creator' AND mv.user_id=v.user_id AND mc.created_at>=datetime('now','-90 days'))
            ORDER BY v.created_at DESC
            LIMIT 500
            """,
            (uid, uid, uid, uid, uid, uid, uid, uid, uid),
        ).fetchall()

        history = c.execute(
            """
            SELECT v.*,
                   CASE WHEN e.action IN ('watch','complete','like','comment','share','save') THEN 1 ELSE -1 END AS signal
            FROM events e JOIN videos v ON v.id=e.video_id
            WHERE e.user_id=? AND e.created_at >= datetime('now','-30 days')
            ORDER BY e.created_at DESC LIMIT 500
            """,
            (uid,),
        ).fetchall()

    videos = [dict(r) for r in rows]
    topic_profile: dict[str, float] = {}
    for row in history:
        topics = infer_topics(_content_text(dict(row)))
        weight = float(row["signal"] or 0)
        for topic in topics:
            topic_profile[topic] = topic_profile.get(topic, 0.0) + weight

    signals = {}
    for video in videos:
        vid = str(video["id"])
        topics = infer_topics(_content_text(video))
        topic_affinity = sum(topic_profile.get(topic, 0.0) for topic in topics)
        signals[vid] = {
            "watch_score": float(video.pop("watch_score") or 0),
            "liked": bool(video.pop("liked")),
            "followed_creator": bool(video.pop("followed_creator")),
            "creator_affinity": float(video.pop("creator_affinity") or 0),
            "topic_affinity": topic_affinity,
            "seen": bool(video.pop("seen")),
            "recent_creator": bool(video.pop("recent_creator")),
        }

    ranked = rank_videos(videos, signals)
    page = ranked[offset:offset + limit]
    return {
        "items": page,
        "personalized": True,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < len(ranked),
        "topic_profile": sorted(topic_profile, key=topic_profile.get, reverse=True)[:5],
    }
