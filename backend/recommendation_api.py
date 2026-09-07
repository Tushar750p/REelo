from fastapi import APIRouter, Header, HTTPException

from main import current_user, db
from recommendation_engine import rank_videos

router = APIRouter(prefix="/api")


@router.get("/recommendations")
def recommendations(limit: int = 20, authorization: str | None = Header(default=None)):
    """Personalized For You candidates using persisted behavior and creator affinity."""
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")

    limit = max(1, min(limit, 50))
    with db() as c:
        rows = c.execute(
            """
            SELECT v.*, u.username, u.display_name,
                   CASE WHEN l.user_id IS NULL THEN 0 ELSE 1 END AS liked,
                   CASE WHEN f.follower_id IS NULL THEN 0 ELSE 1 END AS followed_creator,
                   COALESCE((
                       SELECT SUM(
                           CASE
                               WHEN e.action IN ('watch','complete') THEN MIN(COALESCE(e.seconds,0), 30.0) / 6.0
                               WHEN e.action IN ('skip','dismiss') THEN -2.5
                               WHEN e.action IN ('like','comment','share','save') THEN 2.0
                               ELSE 0
                           END
                       )
                       FROM events e WHERE e.user_id=? AND e.video_id=v.id
                   ), 0) AS watch_score,
                   COALESCE((
                       SELECT SUM(
                           CASE
                               WHEN e.action IN ('watch','complete') THEN MIN(COALESCE(e.seconds,0), 30.0) / 30.0
                               WHEN e.action IN ('like','comment','share','save') THEN 1.5
                               WHEN e.action IN ('skip','dismiss') THEN -0.75
                               ELSE 0
                           END
                       )
                       FROM events e
                       JOIN videos hv ON hv.id=e.video_id
                       WHERE e.user_id=? AND hv.user_id=v.user_id AND hv.id<>v.id
                   ), 0) AS creator_affinity,
                   CASE WHEN EXISTS(
                       SELECT 1 FROM events e2 WHERE e2.user_id=? AND e2.video_id=v.id
                   ) THEN 1 ELSE 0 END AS seen,
                   CASE WHEN EXISTS(
                       SELECT 1 FROM events e3
                       JOIN videos rv ON rv.id=e3.video_id
                       WHERE e3.user_id=? AND rv.user_id=v.user_id
                         AND e3.created_at >= datetime('now','-24 hours')
                   ) THEN 1 ELSE 0 END AS recent_creator
            FROM videos v
            JOIN users u ON u.id=v.user_id
            LEFT JOIN likes l ON l.video_id=v.id AND l.user_id=?
            LEFT JOIN follows f ON f.following_id=v.user_id AND f.follower_id=?
            WHERE v.status='ready'
            ORDER BY v.created_at DESC
            LIMIT 200
            """,
            (uid, uid, uid, uid, uid, uid),
        ).fetchall()

    videos = [dict(r) for r in rows]
    signals = {
        str(v["id"]): {
            "watch_score": float(v.pop("watch_score") or 0),
            "liked": bool(v.pop("liked")),
            "followed_creator": bool(v.pop("followed_creator")),
            "creator_affinity": float(v.pop("creator_affinity") or 0),
            "seen": bool(v.pop("seen")),
            "recent_creator": bool(v.pop("recent_creator")),
        }
        for v in videos
    }
    ranked = rank_videos(videos, signals)[:limit]
    return {"items": ranked, "personalized": True, "limit": limit}
