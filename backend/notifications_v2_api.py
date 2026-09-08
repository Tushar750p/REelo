from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException

from main import current_user, db

router = APIRouter(prefix="/api/notifications", tags=["notifications-v2"])


def _uid(authorization: str | None) -> str:
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def _group_key(row: dict) -> str:
    video = str(row.get("video_id") or "")
    actor = str(row.get("actor_id") or "")
    return f"{row.get('type','unknown')}:{video or actor}"


def _label(type_: str, count: int, actor: str | None = None) -> str:
    names = {
        "like": "liked your video",
        "comment": "commented on your video",
        "follow": "started following you",
        "mention": "mentioned you",
        "reply": "replied to your comment",
        "gift": "sent you a gift",
        "verification": "updated your verification status",
    }
    base = names.get(type_, "sent you an activity update")
    if count > 1 and type_ == "like":
        return f"{count} people liked your video"
    return base


@router.get("")
def notifications_v2(limit: int = 30, offset: int = 0, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    with db() as c:
        rows = c.execute("""SELECT n.id,n.recipient_id,n.actor_id,n.type,n.video_id,n.read,n.created_at,
            u.username actor_username,u.display_name actor_display_name
            FROM notifications n JOIN users u ON u.id=n.actor_id
            WHERE n.recipient_id=? ORDER BY n.created_at DESC LIMIT ? OFFSET ?""", (uid, limit * 3, offset)).fetchall()
        unread = c.execute("SELECT COUNT(*) FROM notifications WHERE recipient_id=? AND read=0", (uid,)).fetchone()[0]
        total = c.execute("SELECT COUNT(*) FROM notifications WHERE recipient_id=?", (uid,)).fetchone()[0]

    grouped = []
    seen = set()
    for raw in rows:
        row = dict(raw); key = _group_key(row)
        if key in seen:
            continue
        seen.add(key)
        related = [dict(x) for x in rows if _group_key(dict(x)) == key]
        actors = []
        for item in related:
            name = item.get("actor_display_name") or item.get("actor_username")
            if name and name not in actors:
                actors.append(name)
        row["group_count"] = len(related)
        row["actors"] = actors[:5]
        row["message"] = _label(row.get("type", ""), len(related))
        row["is_read"] = bool(row.pop("read", 0))
        grouped.append(row)
        if len(grouped) >= limit:
            break
    return {"items": grouped, "unread": unread, "total": total, "limit": limit, "offset": offset, "version": "2.0"}


@router.post("/read-all")
def mark_all_read(authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    with db() as c:
        c.execute("UPDATE notifications SET read=1 WHERE recipient_id=? AND read=0", (uid,))
    return {"ok": True, "unread": 0}


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    with db() as c:
        updated = c.execute("UPDATE notifications SET read=1 WHERE id=? AND recipient_id=?", (notification_id, uid)).rowcount
        if not updated:
            raise HTTPException(404, "Notification not found")
        unread = c.execute("SELECT COUNT(*) FROM notifications WHERE recipient_id=? AND read=0", (uid,)).fetchone()[0]
    return {"ok": True, "unread": unread}


@router.get("/summary")
def notification_summary(authorization: str | None = Header(default=None)):
    uid = _uid(authorization)
    with db() as c:
        rows = c.execute("SELECT type,COUNT(*) count FROM notifications WHERE recipient_id=? AND read=0 GROUP BY type ORDER BY count DESC", (uid,)).fetchall()
        recent = c.execute("SELECT id,type,created_at FROM notifications WHERE recipient_id=? ORDER BY created_at DESC LIMIT 10", (uid,)).fetchall()
    return {"unread": sum(int(r["count"]) for r in rows), "by_type": {r["type"]: int(r["count"]) for r in rows}, "recent": [dict(r) for r in recent], "version": "2.0"}
