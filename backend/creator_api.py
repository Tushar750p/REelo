from fastapi import APIRouter, Header, HTTPException
from main import db, current_user

router = APIRouter(prefix="/api/creator", tags=["creator"])

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
        return {"creator":dict(user),"totals":dict(totals),"videos":[dict(r) for r in recent]}

@router.get("/analytics")
def analytics(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    with db() as c:
        rows = c.execute("SELECT substr(created_at,1,10) day,COUNT(*) videos,COALESCE(SUM(views),0) views,COALESCE(SUM(likes),0) likes,COALESCE(SUM(comments),0) comments FROM videos WHERE user_id=? GROUP BY substr(created_at,1,10) ORDER BY day DESC LIMIT 30", (uid,)).fetchall()
    return {"items":[dict(r) for r in rows]}
