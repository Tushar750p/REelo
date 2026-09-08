-- REelo PostgreSQL integrity hardening migration 002.
-- Adds database-enforced invariants and query indexes that protect counters,
-- notification state, and event data under concurrent application writes.

ALTER TABLE users
    ADD CONSTRAINT users_followers_nonnegative CHECK (followers >= 0),
    ADD CONSTRAINT users_following_nonnegative CHECK (following >= 0);

ALTER TABLE videos
    ADD CONSTRAINT videos_likes_nonnegative CHECK (likes >= 0),
    ADD CONSTRAINT videos_comments_nonnegative CHECK (comments >= 0),
    ADD CONSTRAINT videos_views_nonnegative CHECK (views >= 0),
    ADD CONSTRAINT videos_file_size_nonnegative CHECK (file_size >= 0);

ALTER TABLE events
    ADD CONSTRAINT events_seconds_nonnegative CHECK (seconds >= 0);

ALTER TABLE notifications
    ADD CONSTRAINT notifications_read_boolean CHECK (read IN (0, 1));

CREATE INDEX IF NOT EXISTS idx_likes_user ON likes(user_id);
CREATE INDEX IF NOT EXISTS idx_follows_follower ON follows(follower_id);
CREATE INDEX IF NOT EXISTS idx_comments_user_created ON comments(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread
    ON notifications(recipient_id, created_at DESC)
    WHERE read = 0;
CREATE INDEX IF NOT EXISTS idx_events_video_created
    ON events(video_id, created_at DESC);
