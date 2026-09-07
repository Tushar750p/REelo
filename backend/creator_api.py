from fastapi import APIRouter, Header, HTTPException
from main import db, current_user

router = APIRouter(prefix="/api/creator", tags=["creator"])


def ensure_follower_history(c):
    c.execute("CREATE TABLE IF NOT EXISTS creator_follower_history(creator_id TEXT NOT NULL,day TEXT NOT NULL,followers INTEGER NOT NULL,PRIMARY KEY(creator_id,day))")


@router.get("/dashboard")
def dashboard(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    with db() as c:
        user = c.execute("SELECT id,username,display_name,bio,followers,following FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")
        totals = c.execute("SELECT COUNT(*) videos,COALESCE(SUM(views),0) views,COALESCE(SUM(likes),0) likes,COALESCE(SUM(comments),0) comments FROM videos WHERE user_id=?", (uid,)).fetchone()
        recent = c.execute("SELECT id,filename,caption,likes,comments,views,status,created_at FROM videos WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (uid,)).fetchall()
        videos = [dict(r) for r in recent]
        for video in videos:
            views = max(0, int(video.get("views") or 0))
            video["engagement_rate"] = round(((int(video.get("likes") or 0) + int(video.get("comments") or 0)) / views) * 100, 2) if views else 0.0
        top = sorted(videos, key=lambda v: (v["engagement_rate"], int(v.get("views") or 0)), reverse=True)[:5]
        return {"creator": dict(user), "totals": dict(totals), "videos": videos, "top_videos": top}


@router.get("/analytics")
def analytics(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    with db() as c:
        ensure_follower_history(c)
        user = c.execute("SELECT followers FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")
        c.execute("INSERT INTO creator_follower_history(creator_id,day,followers) VALUES(?,date('now'),?) ON CONFLICT(creator_id,day) DO UPDATE SET followers=excluded.followers", (uid, int(user["followers"] or 0)))
        rows = c.execute("SELECT substr(created_at,1,10) day,COUNT(*) videos,COALESCE(SUM(views),0) views,COALESCE(SUM(likes),0) likes,COALESCE(SUM(comments),0) comments FROM videos WHERE user_id=? GROUP BY substr(created_at,1,10) ORDER BY day ASC LIMIT 30", (uid,)).fetchall()
        follower_rows = c.execute("SELECT day,followers FROM creator_follower_history WHERE creator_id=? ORDER BY day ASC LIMIT 90", (uid,)).fetchall()
        top_rows = c.execute("SELECT id,filename,caption,views,likes,comments,created_at FROM videos WHERE user_id=? ORDER BY (likes+comments) DESC,views DESC LIMIT 5", (uid,)).fetchall()
    daily = [dict(r) for r in rows]
    for item in daily:
        views = max(0, int(item.get("views") or 0))
        item["engagement_rate"] = round(((int(item.get("likes") or 0) + int(item.get("comments") or 0)) / views) * 100, 2) if views else 0.0
    followers = [dict(r) for r in follower_rows]
    for i, item in enumerate(followers):
        previous = followers[i - 1]["followers"] if i else item["followers"]
        item["growth"] = item["followers"] - previous
    return {"items": daily, "followers": followers, "top_videos": [dict(r) for r in top_rows]}
