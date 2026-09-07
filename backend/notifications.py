from uuid import uuid4

def ensure_notifications_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,recipient_id TEXT NOT NULL,actor_id TEXT NOT NULL,type TEXT NOT NULL,video_id TEXT,read INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")

def add_notification(c, recipient_id, actor_id, type_, video_id=None):
    if not recipient_id or recipient_id == actor_id:
        return
    ensure_notifications_table(c)
    c.execute("INSERT INTO notifications(id,recipient_id,actor_id,type,video_id) VALUES(?,?,?,?,?)", (uuid4().hex, recipient_id, actor_id, type_, video_id))
