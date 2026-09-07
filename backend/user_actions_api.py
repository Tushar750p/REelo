from fastapi import APIRouter, Header, HTTPException
from main import app, db, current_user

router = APIRouter(prefix="/api/user-actions", tags=["user-actions"])


def require_user(authorization: str | None):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_blocks_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS blocks(blocker_id TEXT NOT NULL,blocked_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(blocker_id,blocked_id))")


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        row = c.execute("SELECT user_id,video_id FROM comments WHERE id=?", (comment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Comment not found")
        if row["user_id"] != uid:
            raise HTTPException(403, "You can only delete your own comments")
        c.execute("DELETE FROM comments WHERE id=?", (comment_id,))
        c.execute("UPDATE videos SET comments=MAX(comments-1,0) WHERE id=?", (row["video_id"],))
    return {"ok": True, "comment_id": comment_id}


@router.post("/users/{user_id}/block")
def toggle_block(user_id: str, authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    if uid == user_id:
        raise HTTPException(400, "Cannot block yourself")
    with db() as c:
        if not c.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
            raise HTTPException(404, "User not found")
        ensure_blocks_table(c)
        existing = c.execute("SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?", (uid, user_id)).fetchone()
        if existing:
            c.execute("DELETE FROM blocks WHERE blocker_id=? AND blocked_id=?", (uid, user_id))
            action = "unblock"
        else:
            c.execute("INSERT INTO blocks(blocker_id,blocked_id) VALUES(?,?)", (uid, user_id))
            action = "block"
    return {"ok": True, "action": action, "user_id": user_id}


@router.get("/blocked")
def blocked_users(authorization: str | None = Header(default=None)):
    uid = require_user(authorization)
    with db() as c:
        ensure_blocks_table(c)
        rows = c.execute("SELECT u.id,u.username,u.display_name,b.created_at FROM blocks b JOIN users u ON u.id=b.blocked_id WHERE b.blocker_id=? ORDER BY b.created_at DESC", (uid,)).fetchall()
    return {"items": [dict(r) for r in rows]}


app.include_router(router)
