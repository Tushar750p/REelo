from fastapi import APIRouter, Header, HTTPException
from main import current_user, db

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def auth_user(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


@router.get("/{username}")
def get_profile(username: str, authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    username = username.strip().lstrip("@").lower()
    if not username or len(username) > 30:
        raise HTTPException(400, "Invalid username")
    with db() as c:
        user = c.execute(
            "SELECT id,username,display_name,bio,followers,following,created_at FROM users WHERE username=?",
            (username,),
        ).fetchone()
        if not user:
            raise HTTPException(404, "Profile not found")
        followed = bool(uid and c.execute(
            "SELECT 1 FROM follows WHERE follower_id=? AND following_id=?",
            (uid, user["id"]),
        ).fetchone())
        videos = c.execute(
            "SELECT id,user_id,filename,caption,likes,comments,views,created_at FROM videos WHERE user_id=? AND status='ready' ORDER BY created_at DESC LIMIT 60",
            (user["id"],),
        ).fetchall()
    return {"user": dict(user), "followed": followed, "is_me": bool(uid and uid == user["id"]), "videos": [dict(v) for v in videos]}


@router.get("/id/{user_id}")
def get_profile_by_id(user_id: str, authorization: str | None = Header(default=None)):
    with db() as c:
        row = c.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Profile not found")
    return get_profile(row["username"], authorization)


@router.get("/{username}/followers")
def followers(username: str, limit: int = 50, offset: int = 0):
    username = username.strip().lstrip("@").lower()
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    with db() as c:
        user = c.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not user: raise HTTPException(404, "Profile not found")
        rows = c.execute(
            "SELECT u.id,u.username,u.display_name,u.bio,u.followers,u.following FROM follows f JOIN users u ON u.id=f.follower_id WHERE f.following_id=? ORDER BY f.rowid DESC LIMIT ? OFFSET ?",
            (user["id"], limit, offset),
        ).fetchall()
    return {"items": [dict(r) for r in rows], "limit": limit, "offset": offset}


@router.get("/{username}/following")
def following(username: str, limit: int = 50, offset: int = 0):
    username = username.strip().lstrip("@").lower()
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    with db() as c:
        user = c.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not user: raise HTTPException(404, "Profile not found")
        rows = c.execute(
            "SELECT u.id,u.username,u.display_name,u.bio,u.followers,u.following FROM follows f JOIN users u ON u.id=f.following_id WHERE f.follower_id=? ORDER BY f.rowid DESC LIMIT ? OFFSET ?",
            (user["id"], limit, offset),
        ).fetchall()
    return {"items": [dict(r) for r in rows], "limit": limit, "offset": offset}
