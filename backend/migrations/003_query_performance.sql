-- REelo PostgreSQL query-performance migration 003.
-- Indexes are aligned with the current feed, like-state, and ready-video
-- query shapes. Partial indexes avoid indexing non-ready videos.

CREATE INDEX IF NOT EXISTS idx_videos_ready_created
    ON videos(created_at DESC)
    WHERE status = 'ready';

CREATE INDEX IF NOT EXISTS idx_videos_user_ready_created
    ON videos(user_id, created_at DESC)
    WHERE status = 'ready';

CREATE INDEX IF NOT EXISTS idx_likes_video_user
    ON likes(video_id, user_id);

ANALYZE users;
ANALYZE videos;
ANALYZE likes;
ANALYZE follows;
ANALYZE comments;
ANALYZE events;
ANALYZE notifications;
