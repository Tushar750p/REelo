from fastapi import APIRouter, Header, HTTPException

from main import current_user, db, MEDIA
from recommendation_engine import rank_videos
from content_topics import infer_topics
from video_processing import ensure_tables, process_video

router = APIRouter(prefix="/api")


def _content_text(video: dict) -> str:
    keys = ("title", "caption", "description", "text", "hashtags", "tags")
    values = []
    for key in keys:
        value = video.get(key)
        if isinstance(value, (list, tuple)):
            values.extend(str(x) for x in value)
        elif value:
            values.append(str(value))
    return " ".join(values)


@router.get("/recommendations")
def recommendations(limit: int = 20, offset: int = 0, authorization: str | None = Header(default=None)):
    """Personalized candidates with behavior, negative feedback and session-aware diversity."""
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    limit = max(1, min(limit, 50)); offset = max(0, min(offset, 5000))
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS blocked_users(blocker_id TEXT NOT NULL, blocked_id TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(blocker_id,blocked_id))")
        rows = c.execute("""SELECT v.*,u.username,u.display_name,
        CASE WHEN l.user_id IS NULL THEN 0 ELSE 1 END liked,
        CASE WHEN f.follower_id IS NULL THEN 0 ELSE 1 END followed_creator,
        COALESCE((SELECT SUM(CASE WHEN e.action IN ('watch','complete') THEN MIN(COALESCE(e.seconds,0),30.0)/6.0 WHEN e.action IN ('skip','dismiss') THEN -2.5 WHEN e.action IN ('like','comment','share','save') THEN 2.0 ELSE 0 END) FROM events e WHERE e.user_id=? AND e.video_id=v.id),0) watch_score,
        COALESCE((SELECT SUM(CASE WHEN e.action IN ('watch','complete') THEN MIN(COALESCE(e.seconds,0),30.0)/30.0 WHEN e.action IN ('like','comment','share','save') THEN 1.5 WHEN e.action IN ('skip','dismiss') THEN -0.75 ELSE 0 END) FROM events e JOIN videos hv ON hv.id=e.video_id WHERE e.user_id=? AND hv.user_id=v.user_id AND hv.id<>v.id),0) creator_affinity,
        CASE WHEN EXISTS(SELECT 1 FROM events e2 WHERE e2.user_id=? AND e2.video_id=v.id) THEN 1 ELSE 0 END seen,
        CASE WHEN EXISTS(SELECT 1 FROM events e3 JOIN videos rv ON rv.id=e3.video_id WHERE e3.user_id=? AND rv.user_id=v.user_id AND e3.created_at>=datetime('now','-24 hours')) THEN 1 ELSE 0 END recent_creator,
        COALESCE((SELECT SUM(CASE WHEN e.action IN ('not_interested','skip','dismiss') THEN -1.0 ELSE 0 END) FROM events e WHERE e.user_id=? AND e.video_id=v.id AND e.created_at>=datetime('now','-90 days')),0) negative_feedback,
        CASE WHEN EXISTS(SELECT 1 FROM events en WHERE en.user_id=? AND en.video_id=v.id AND en.action IN ('not_interested','skip','dismiss') AND en.created_at>=datetime('now','-7 days')) THEN 1 ELSE 0 END recent_negative
        FROM videos v JOIN users u ON u.id=v.user_id LEFT JOIN likes l ON l.video_id=v.id AND l.user_id=? LEFT JOIN follows f ON f.following_id=v.user_id AND f.follower_id=?
        WHERE v.status='ready' AND v.user_id<>? AND NOT EXISTS(SELECT 1 FROM blocked_users b WHERE b.blocker_id=? AND b.blocked_id=v.user_id)
        AND NOT EXISTS(SELECT 1 FROM events ni WHERE ni.user_id=? AND ni.video_id=v.id AND ni.action='not_interested' AND ni.created_at>=datetime('now','-90 days'))
        AND NOT EXISTS(SELECT 1 FROM events mc JOIN videos mv ON mv.id=mc.video_id WHERE mc.user_id=? AND mc.action='mute_creator' AND mv.user_id=v.user_id AND mc.created_at>=datetime('now','-90 days'))
        ORDER BY v.created_at DESC LIMIT 500""", (uid,uid,uid,uid,uid,uid,uid,uid,uid,uid,uid)).fetchall()
        history = c.execute("SELECT v.*,e.action,CASE WHEN e.action IN ('watch','complete','like','comment','share','save') THEN 1 WHEN e.action IN ('not_interested','skip','dismiss','mute_creator') THEN -1 ELSE 0 END signal FROM events e JOIN videos v ON v.id=e.video_id WHERE e.user_id=? AND e.created_at>=datetime('now','-30 days') ORDER BY e.created_at DESC LIMIT 500", (uid,)).fetchall()
    topic_profile={}
    for row in history:
        for topic in infer_topics(_content_text(dict(row))): topic_profile[topic]=topic_profile.get(topic,0.0)+float(row['signal'] or 0)
    videos=[]; signals={}
    for raw in rows:
        video=dict(raw); vid=str(video['id']); topics=infer_topics(_content_text(video)); video['_topics']=topics
        signals[vid]={'watch_score':float(video.pop('watch_score') or 0),'liked':bool(video.pop('liked')),'followed_creator':bool(video.pop('followed_creator')),'creator_affinity':float(video.pop('creator_affinity') or 0),'topic_affinity':sum(topic_profile.get(t,0.0) for t in topics),'seen':bool(video.pop('seen')),'recent_creator':bool(video.pop('recent_creator')),'negative_feedback':float(video.pop('negative_feedback') or 0),'recent_negative':bool(video.pop('recent_negative'))}
        videos.append(video)
    session_creator_counts={}; session_topics={}
    for row in history[:50]:
        d=dict(row); creator=str(d.get('user_id') or '')
        if creator: session_creator_counts[creator]=session_creator_counts.get(creator,0)+1
        if int(d.get('signal') or 0)>0:
            for topic in infer_topics(_content_text(d)): session_topics[topic]=session_topics.get(topic,0.0)+0.35
    ranked=rank_videos(videos,signals,session_creator_counts,session_topics); page=ranked[offset:offset+limit]
    return {'items':page,'personalized':True,'limit':limit,'offset':offset,'has_more':offset+len(page)<len(ranked),'topic_profile':sorted(topic_profile,key=topic_profile.get,reverse=True)[:5],'ranking_version':'2.0'}


@router.get("/videos/{video_id}/processing")
def processing_status(video_id: str, authorization: str | None = Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,"Login required")
    with db() as c:
        ensure_tables(c)
        row=c.execute("SELECT v.id,v.user_id,v.filename,p.status,p.duration_seconds,p.width,p.height,p.thumbnail,p.error FROM videos v LEFT JOIN video_processing p ON p.video_id=v.id WHERE v.id=? AND v.user_id=?",(video_id,uid)).fetchone()
        if not row: raise HTTPException(404,"Video not found")
        variants=c.execute("SELECT profile,filename,width,height,mime_type FROM video_variants WHERE video_id=? ORDER BY CASE profile WHEN '360p' THEN 1 WHEN '540p' THEN 2 WHEN '720p' THEN 3 ELSE 4 END",(video_id,)).fetchall()
    result=dict(row); result['thumbnail_url']=f"/media/{result['thumbnail']}" if result.get('thumbnail') else None; result['variants']=[{**dict(v),'url':f"/media/{v['filename']}"} for v in variants]; return result


@router.post("/videos/{video_id}/process")
def process_uploaded_video(video_id: str, authorization: str | None = Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,"Login required")
    with db() as c:
        ensure_tables(c); row=c.execute("SELECT id,filename,user_id FROM videos WHERE id=? AND user_id=?",(video_id,uid)).fetchone()
        if not row: raise HTTPException(404,"Video not found")
        source=MEDIA/row['filename']
    if not source.exists(): raise HTTPException(404,"Source video file is missing")
    try: return process_video(video_id,source)
    except Exception as exc:
        with db() as c:
            ensure_tables(c); c.execute("INSERT INTO video_processing(video_id,status,error,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(video_id) DO UPDATE SET status='failed',error=excluded.error,updated_at=CURRENT_TIMESTAMP",(video_id,'failed',str(exc)[:1000]))
        raise HTTPException(500,"Video processing failed")
