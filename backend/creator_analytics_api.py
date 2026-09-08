from fastapi import APIRouter, Header, HTTPException
from main import db, current_user
import re
from collections import Counter

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


def format_hour(hour):
    hour = int(hour)
    suffix = "AM" if hour < 12 else "PM"
    display = hour % 12 or 12
    return f"{display}:00 {suffix}"


def period_metrics(c, uid, days):
    row = c.execute("""
        SELECT COUNT(CASE WHEN e.action='view' THEN 1 END) views,
               COUNT(CASE WHEN e.action='like' THEN 1 END) likes,
               COUNT(CASE WHEN e.action='comment' THEN 1 END) comments,
               COUNT(CASE WHEN e.action='share' THEN 1 END) shares,
               COUNT(CASE WHEN e.action='save' THEN 1 END) saves,
               COALESCE(SUM(CASE WHEN e.action IN ('view','watch','progress','complete') THEN e.seconds ELSE 0 END),0) watch_seconds,
               COUNT(DISTINCT CASE WHEN e.user_id!='anonymous' AND e.action='view' THEN e.user_id END) unique_viewers
        FROM events e JOIN videos v ON v.id=e.video_id
        WHERE v.user_id=? AND e.created_at>=date('now',?)
    """, (uid, f'-{max(1, days)-1} day')).fetchone()
    d = dict(row)
    d['interactions'] = int(d['likes'] or 0) + int(d['comments'] or 0) + int(d['shares'] or 0) + int(d['saves'] or 0)
    d['engagement_rate'] = engagement(d['likes'], d['comments'], d['views'], d['saves'], d['shares'])
    return d


def theme_tokens(text):
    words = re.findall(r"[a-zA-Z0-9]{4,}", (text or '').lower())
    stop = {'this','that','with','from','your','have','will','just','like','what','when','where','into','about','then','than','they','them','are','for','and','the','you','video','reel'}
    return [w for w in words if w not in stop]


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


@router.get("/comparison")
def comparison(days: int = 7, compare_days: int = 30, authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization); days = max(1, min(days, 30)); compare_days = max(days + 1, min(compare_days, 90))
    with db() as c:
        current = period_metrics(c, uid, days)
        previous = c.execute("""
            SELECT COUNT(CASE WHEN e.action='view' THEN 1 END) views,
                   COUNT(CASE WHEN e.action='like' THEN 1 END) likes,
                   COUNT(CASE WHEN e.action='comment' THEN 1 END) comments,
                   COUNT(CASE WHEN e.action='share' THEN 1 END) shares,
                   COUNT(CASE WHEN e.action='save' THEN 1 END) saves,
                   COALESCE(SUM(CASE WHEN e.action IN ('view','watch','progress','complete') THEN e.seconds ELSE 0 END),0) watch_seconds,
                   COUNT(DISTINCT CASE WHEN e.user_id!='anonymous' AND e.action='view' THEN e.user_id END) unique_viewers
            FROM events e JOIN videos v ON v.id=e.video_id
            WHERE v.user_id=? AND e.created_at>=date('now',?) AND e.created_at<date('now',?)
        """, (uid, f'-{compare_days-1} day', f'-{days} day')).fetchone()
    old = dict(previous); old['interactions'] = sum(int(old[k] or 0) for k in ('likes','comments','shares','saves')); old['engagement_rate'] = engagement(old['likes'],old['comments'],old['views'],old['saves'],old['shares'])
    def delta(a,b): return round(((float(a)-float(b))/float(b))*100,1) if b else None
    return {"current_days": days, "comparison_window_days": compare_days-days, "current": current, "previous": old, "changes": {k: delta(current[k], old[k]) for k in ('views','interactions','watch_seconds','unique_viewers','engagement_rate')}}


@router.get("/video-performance")
def video_performance(authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization)
    with db() as c:
        rows = c.execute("""
            SELECT v.id,v.caption,v.created_at,v.views,v.likes,v.comments,
                   COALESCE((SELECT SUM(e.seconds) FROM events e WHERE e.video_id=v.id AND e.action IN ('view','watch','progress','complete')),0) watch_seconds,
                   COALESCE((SELECT COUNT(DISTINCT e.user_id) FROM events e WHERE e.video_id=v.id AND e.user_id!='anonymous' AND e.action='view'),0) unique_viewers
            FROM videos v WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 50
        """, (uid,)).fetchall()
    items=[]
    for r in rows:
        v=dict(r); views=int(v['views'] or 0); likes=int(v['likes'] or 0); comments=int(v['comments'] or 0)
        rate=engagement(likes,comments,views); avg=round(float(v['watch_seconds'] or 0)/max(views,1),2)
        score=round(min(100, rate*8 + min(40, views/10) + min(20, avg*2)),1)
        v.update(interaction_rate=rate,avg_watch_seconds=avg,performance_score=score,score_note='Relative score using observed views, like/comment rate and average watch seconds; not a prediction.')
        items.append(v)
    return {"items":items}


@router.get("/viewer-cohorts")
def viewer_cohorts(authorization: str | None = Header(default=None)):
    uid=uid_or_401(authorization)
    with db() as c:
        rows=c.execute("""
            SELECT e.user_id,MIN(e.created_at) first_seen,MAX(e.created_at) last_seen,COUNT(CASE WHEN e.action='view' THEN 1 END) views
            FROM events e JOIN videos v ON v.id=e.video_id
            WHERE v.user_id=? AND e.user_id!='anonymous'
            GROUP BY e.user_id
        """,(uid,)).fetchall()
    from datetime import datetime, timedelta
    cutoff=(datetime.utcnow()-timedelta(days=30)).strftime('%Y-%m-%d')
    new=sum(1 for r in rows if str(r['first_seen'])[:10]>=cutoff); returning=sum(1 for r in rows if str(r['first_seen'])[:10]<cutoff)
    return {"period_days":30,"new_viewers":new,"returning_viewers":returning,"total_identified_viewers":len(rows),"note":"New means first observed creator interaction in the last 30 days; anonymous viewers are excluded."}


@router.get("/content-performance")
def content_performance(authorization: str | None = Header(default=None)):
    uid=uid_or_401(authorization)
    with db() as c:
        rows=c.execute("SELECT id,caption,views,likes,comments,created_at FROM videos WHERE user_id=? ORDER BY created_at DESC LIMIT 100",(uid,)).fetchall()
    stats={}
    for r in rows:
        for token in set(theme_tokens(r['caption'])):
            s=stats.setdefault(token,{'theme':token,'videos':0,'views':0,'likes':0,'comments':0})
            s['videos']+=1;s['views']+=int(r['views'] or 0);s['likes']+=int(r['likes'] or 0);s['comments']+=int(r['comments'] or 0)
    items=[]
    for s in stats.values():
        if s['videos']<1: continue
        s['interaction_rate']=engagement(s['likes'],s['comments'],s['views']);items.append(s)
    items.sort(key=lambda x:(x['interaction_rate'],x['views']),reverse=True)
    return {"items":items[:12],"method":"caption_keyword_themes","note":"Themes are simple normalized caption keywords, not automated topic classification."}


@router.get("/posting-heatmap")
def posting_heatmap(authorization: str | None = Header(default=None)):
    uid=uid_or_401(authorization)
    with db() as c:
        rows=c.execute("""
            SELECT CAST(strftime('%w',e.created_at) AS INTEGER) weekday,CAST(strftime('%H',e.created_at) AS INTEGER) hour,
                   COUNT(CASE WHEN e.action='view' THEN 1 END) views,
                   COUNT(CASE WHEN e.action IN ('like','comment','share','save') THEN 1 END) interactions
            FROM events e JOIN videos v ON v.id=e.video_id WHERE v.user_id=? GROUP BY weekday,hour
        """,(uid,)).fetchall()
    cells={(int(r['weekday']),int(r['hour'])):dict(r) for r in rows}
    return {"days":["Sun","Mon","Tue","Wed","Thu","Fri","Sat"],"hours":[format_hour(h) for h in range(24)],"cells":[{"weekday":d,"hour":h,"views":int(cells.get((d,h),{}).get('views',0)),"interactions":int(cells.get((d,h),{}).get('interactions',0))} for d in range(7) for h in range(24)]}


@router.get("/next-content")
def next_content(authorization: str | None = Header(default=None)):
    uid=uid_or_401(authorization)
    with db() as c:
        posting=c.execute("SELECT CAST(strftime('%w',e.created_at) AS INTEGER) weekday,CAST(strftime('%H',e.created_at) AS INTEGER) hour,COUNT(CASE WHEN e.action='view' THEN 1 END) views,COUNT(CASE WHEN e.action IN ('like','comment','share','save') THEN 1 END) interactions FROM events e JOIN videos v ON v.id=e.video_id WHERE v.user_id=? GROUP BY weekday,hour HAVING views>0 ORDER BY views DESC,interactions DESC LIMIT 3",(uid,)).fetchall()
        top=c.execute("SELECT caption,views,likes,comments FROM videos WHERE user_id=? ORDER BY views DESC,likes DESC LIMIT 10",(uid,)).fetchall()
    themes=Counter(t for r in top for t in theme_tokens(r['caption']))
    rec=[]
    if posting: rec.append({"type":"timing","title":"Test your strongest observed time","detail":f"Try your next post around {format_hour(posting[0]['hour'])} on {['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][int(posting[0]['weekday'])]}.","based_on":"observed view activity"})
    if themes: rec.append({"type":"theme","title":"Build on a proven theme","detail":f"Consider another post around '{themes.most_common(1)[0][0]}'.","based_on":"caption theme frequency"})
    if top: rec.append({"type":"format","title":"Repeat what earned reach","detail":"Reuse the strongest video's core format or idea, then test a different opening.","based_on":"highest observed views"})
    if not rec: rec=[{"type":"data","title":"Build more data","detail":"Post more videos and collect view/engagement events to unlock content opportunities."}]
    return {"items":rec,"note":"These are explainable experiments based on your recorded performance, not guaranteed predictions."}


@router.get("/intelligence")
def creator_intelligence(authorization: str | None = Header(default=None)):
    """Explainable creator insights derived only from observed REelo events."""
    uid = uid_or_401(authorization)
    with db() as c:
        posting = c.execute("""
            SELECT CAST(strftime('%w',e.created_at) AS INTEGER) weekday,CAST(strftime('%H',e.created_at) AS INTEGER) hour,
                   COUNT(CASE WHEN e.action='view' THEN 1 END) views,COUNT(CASE WHEN e.action IN ('like','comment','share','save') THEN 1 END) interactions,COALESCE(SUM(e.seconds),0) watch_seconds
            FROM events e JOIN videos v ON v.id=e.video_id WHERE v.user_id=? GROUP BY weekday,hour HAVING views > 0 ORDER BY views DESC, interactions DESC LIMIT 12
        """, (uid,)).fetchall()
        videos = c.execute("SELECT v.id,v.caption,v.created_at,v.views,v.likes,v.comments,COALESCE((SELECT SUM(e.seconds) FROM events e WHERE e.video_id=v.id),0) watch_seconds FROM videos v WHERE v.user_id=? ORDER BY v.views DESC,v.likes DESC LIMIT 20", (uid,)).fetchall()
        event_count = c.execute("SELECT COUNT(*) FROM events e JOIN videos v ON v.id=e.video_id WHERE v.user_id=?", (uid,)).fetchone()[0]
    rows=[dict(x) for x in posting]; insights=[]
    if rows:
        b=rows[0]; insights.append({"type":"posting_time","title":"Your strongest observed posting window","detail":f"{format_hour(b['hour'])} on {['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][int(b['weekday'])]} has the most recorded views.","weekday":int(b['weekday']),"hour":int(b['hour']),"views":int(b['views']),"interactions":int(b['interactions'])})
    scored=[]
    for v in videos:
        d=dict(v);views=int(d['views'] or 0); rate=engagement(d['likes'],d['comments'],views);d['interaction_rate']=rate;scored.append(d)
    if scored:
        reach=max(scored,key=lambda x:x['views']);eng=max(scored,key=lambda x:(x['interaction_rate'],x['views']))
        insights.append({"type":"content","title":"Best engagement signal","detail":"Strongest observed like/comment rate among recent videos.","video_id":eng['id'],"rate":eng['interaction_rate']})
        insights.append({"type":"content","title":"Best reach","detail":"Highest-viewed recent video.","video_id":reach['id'],"views":int(reach['views'] or 0)})
    return {"data_quality":{"event_count":int(event_count),"video_count":len(videos),"method":"observed_events_only"},"best_posting_windows":[{"weekday":int(r['weekday']),"hour":int(r['hour']),"label":f"{['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][int(r['weekday'])]} · {format_hour(r['hour'])}","views":int(r['views']),"interactions":int(r['interactions']),"watch_seconds":round(float(r['watch_seconds'] or 0),2)} for r in rows[:6]],"insights":insights,"note":"Insights are explainable signals from recorded REelo activity. They are not predictions."}
