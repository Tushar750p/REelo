from fastapi import APIRouter, Header, HTTPException
from main import db, current_user

router = APIRouter(prefix="/api/creator/analytics", tags=["creator-analytics"])


def uid_or_401(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_followers(c, uid):
    c.execute("CREATE TABLE IF NOT EXISTS creator_follower_history(creator_id TEXT NOT NULL,day TEXT NOT NULL,followers INTEGER NOT NULL,PRIMARY KEY(creator_id,day))")
    user = c.execute("SELECT followers FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")
    c.execute("INSERT INTO creator_follower_history(creator_id,day,followers) VALUES(?,date('now'),?) ON CONFLICT(creator_id,day) DO UPDATE SET followers=excluded.followers", (uid, int(user['followers'] or 0)))


def engagement(likes, comments, views, saves=0, shares=0):
    total = int(likes or 0) + int(comments or 0) + int(saves or 0) + int(shares or 0)
    return round(total / int(views or 1) * 100, 2) if views else 0.0


@router.get("/overview")
def overview(authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization)
    with db() as c:
        ensure_followers(c, uid)
        totals = c.execute("SELECT COUNT(*) videos,COALESCE(SUM(views),0) views,COALESCE(SUM(likes),0) likes,COALESCE(SUM(comments),0) comments FROM videos WHERE user_id=?", (uid,)).fetchone()
        watch = c.execute("SELECT COALESCE(SUM(e.seconds),0) seconds,COUNT(DISTINCT CASE WHEN e.user_id!='anonymous' THEN e.user_id END) unique_viewers,COUNT(*) events FROM events e JOIN videos v ON v.id=e.video_id WHERE v.user_id=? AND e.action IN ('view','watch','progress','complete')", (uid,)).fetchone()
        followers = c.execute("SELECT day,followers FROM creator_follower_history WHERE creator_id=? ORDER BY day DESC LIMIT 2", (uid,)).fetchall()
        top = c.execute("SELECT id,caption,views,likes,comments,created_at FROM videos WHERE user_id=? ORDER BY views DESC,likes DESC LIMIT 5", (uid,)).fetchall()
    seconds = float(watch['seconds'] or 0)
    views = int(totals['views'] or 0)
    return {
        "videos": int(totals['videos'] or 0), "views": views,
        "likes": int(totals['likes'] or 0), "comments": int(totals['comments'] or 0),
        "engagement_rate": engagement(totals['likes'], totals['comments'], views),
        "watch_time_seconds": round(seconds, 2), "watch_time_hours": round(seconds / 3600, 2),
        "average_watch_seconds": round(seconds / max(int(watch['events'] or 0), 1), 2),
        "unique_viewers": int(watch['unique_viewers'] or 0),
        "follower_total": int(followers[0]['followers']) if followers else 0,
        "follower_growth": (int(followers[0]['followers']) - int(followers[1]['followers'])) if len(followers) > 1 else 0,
        "top_videos": [dict(x) for x in top],
        "retention_note": "Retention percentages require video-duration or completion telemetry; REelo does not invent them from incomplete data."
    }


@router.get("/views")
def views_series(days: int = 30, authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization); days = max(1, min(days, 90))
    with db() as c:
        rows = c.execute("SELECT substr(e.created_at,1,10) day,COUNT(CASE WHEN e.action='view' THEN 1 END) views,COALESCE(SUM(e.seconds),0) watch_seconds FROM events e JOIN videos v ON v.id=e.video_id WHERE v.user_id=? AND e.created_at>=date('now',?) GROUP BY substr(e.created_at,1,10) ORDER BY day ASC", (uid, f'-{days-1} day')).fetchall()
    return {"days": days, "items": [dict(x) for x in rows]}


@router.get("/engagement")
def engagement_series(days: int = 30, authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization); days = max(1, min(days, 90))
    with db() as c:
        rows = c.execute("SELECT substr(created_at,1,10) day,COALESCE(SUM(CASE WHEN action='like' THEN 1 ELSE 0 END),0) likes,COALESCE(SUM(CASE WHEN action='comment' THEN 1 ELSE 0 END),0) comments,COALESCE(SUM(CASE WHEN action='share' THEN 1 ELSE 0 END),0) shares,COALESCE(SUM(CASE WHEN action='save' THEN 1 ELSE 0 END),0) saves FROM events e JOIN videos v ON v.id=e.video_id WHERE v.user_id=? AND e.created_at>=date('now',?) GROUP BY substr(created_at,1,10) ORDER BY day ASC", (uid, f'-{days-1} day')).fetchall()
    return {"days": days, "items": [dict(x) for x in rows]}


@router.get("/audience")
def audience(authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization)
    with db() as c:
        ensure_followers(c, uid)
        rows = c.execute("SELECT day,followers FROM creator_follower_history WHERE creator_id=? ORDER BY day ASC LIMIT 90", (uid,)).fetchall()
        viewers = c.execute("SELECT COUNT(DISTINCT e.user_id) FROM events e JOIN videos v ON v.id=e.video_id WHERE v.user_id=? AND e.user_id!='anonymous'", (uid,)).fetchone()[0]
    items = [dict(x) for x in rows]
    for i, item in enumerate(items):
        item['growth'] = int(item['followers']) - int(items[i-1]['followers']) if i else 0
    return {"follower_history": items, "unique_viewers": int(viewers or 0)}


@router.get("/retention")
def retention(authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization)
    with db() as c:
        rows = c.execute("SELECT CASE WHEN e.seconds < 3 THEN '0-3s' WHEN e.seconds < 10 THEN '3-10s' WHEN e.seconds < 30 THEN '10-30s' WHEN e.seconds < 60 THEN '30-60s' ELSE '60s+' END bucket,COUNT(*) viewers,COALESCE(SUM(e.seconds),0) seconds FROM events e JOIN videos v ON v.id=e.video_id WHERE v.user_id=? AND e.action IN ('view','watch','progress','complete') GROUP BY bucket ORDER BY CASE bucket WHEN '0-3s' THEN 1 WHEN '3-10s' THEN 2 WHEN '10-30s' THEN 3 WHEN '30-60s' THEN 4 ELSE 5 END", (uid,)).fetchall()
    return {"items": [dict(x) for x in rows], "metric": "watch_depth_seconds", "note": "These are observed watch-depth buckets. Percentage retention is shown only when reliable video-duration telemetry is available."}
