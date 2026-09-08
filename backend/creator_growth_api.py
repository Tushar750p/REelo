from fastapi import APIRouter, Header, HTTPException
from main import db, current_user
from datetime import datetime, timedelta
import re

router = APIRouter(prefix="/api/creator/growth", tags=["creator-growth"])


def uid_or_401(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS creator_growth_goals(
            creator_id TEXT PRIMARY KEY,
            weekly_views INTEGER NOT NULL DEFAULT 0,
            weekly_followers INTEGER NOT NULL DEFAULT 0,
            weekly_interactions INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def metric(c, uid, action_sql, days=7):
    row = c.execute(f"""
        SELECT COALESCE(SUM(CASE WHEN {action_sql} THEN 1 ELSE 0 END),0) value
        FROM events e JOIN videos v ON v.id=e.video_id
        WHERE v.user_id=? AND e.created_at>=date('now',?)
    """, (uid, f"-{max(1, days)-1} day")).fetchone()
    return int(row["value"] or 0)


def followers(c, uid):
    row = c.execute("SELECT followers FROM users WHERE id=?", (uid,)).fetchone()
    return int(row["followers"] or 0) if row else 0


def theme_tokens(text):
    words = re.findall(r"[a-zA-Z0-9]{4,}", (text or "").lower())
    stop = {"this","that","with","from","your","have","will","just","like","what","when","where","into","about","then","than","they","them","are","for","and","the","you","video","reel"}
    return [w for w in words if w not in stop]


def format_hour(hour):
    hour = int(hour)
    return f"{hour % 12 or 12}:00 {'AM' if hour < 12 else 'PM'}"


def pct(current, target):
    if not target:
        return None
    return round(min(100, current / target * 100), 1)


@router.get("/plan")
def growth_plan(authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization)
    with db() as c:
        ensure_table(c)
        row = c.execute("SELECT weekly_views,weekly_followers,weekly_interactions FROM creator_growth_goals WHERE creator_id=?", (uid,)).fetchone()
        goal = dict(row) if row else {"weekly_views": 0, "weekly_followers": 0, "weekly_interactions": 0}
        views = metric(c, uid, "e.action='view'", 7)
        interactions = metric(c, uid, "e.action IN ('like','comment','share','save')", 7)
        current_followers = followers(c, uid)
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        old = c.execute("SELECT followers FROM creator_follower_history WHERE creator_id=? AND day<=? ORDER BY day DESC LIMIT 1", (uid, seven_days_ago)).fetchone()
        follower_gain = max(0, current_followers - int(old["followers"] or current_followers)) if old else 0
        top_times = c.execute("""
            SELECT CAST(strftime('%w',e.created_at) AS INTEGER) weekday,
                   CAST(strftime('%H',e.created_at) AS INTEGER) hour,
                   COUNT(CASE WHEN e.action='view' THEN 1 END) views,
                   COUNT(CASE WHEN e.action IN ('like','comment','share','save') THEN 1 END) interactions
            FROM events e JOIN videos v ON v.id=e.video_id
            WHERE v.user_id=?
            GROUP BY weekday,hour HAVING views>0
            ORDER BY views DESC,interactions DESC LIMIT 3
        """, (uid,)).fetchall()
        top_videos = c.execute("SELECT id,caption,views,likes,comments FROM videos WHERE user_id=? ORDER BY views DESC,likes DESC LIMIT 10", (uid,)).fetchall()
        themes = {}
        for video in top_videos:
            for token in set(theme_tokens(video["caption"])):
                themes[token] = themes.get(token, 0) + 1

    targets = {"weekly_views": int(goal["weekly_views"] or 0), "weekly_followers": int(goal["weekly_followers"] or 0), "weekly_interactions": int(goal["weekly_interactions"] or 0)}
    progress = {
        "weekly_views": {"current": views, "target": targets["weekly_views"], "percent": pct(views, targets["weekly_views"])},
        "weekly_followers": {"current": follower_gain, "target": targets["weekly_followers"], "percent": pct(follower_gain, targets["weekly_followers"])},
        "weekly_interactions": {"current": interactions, "target": targets["weekly_interactions"], "percent": pct(interactions, targets["weekly_interactions"])},
    }

    actions = []
    if top_times:
        day_names = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
        actions.append({"type":"timing","priority":"high","title":"Use a proven posting window","detail":f"Test your next post around {format_hour(top_times[0]['hour'])} on {day_names[int(top_times[0]['weekday'])]}.","evidence":"highest observed creator view activity"})
    if themes:
        theme = sorted(themes.items(), key=lambda x: x[1], reverse=True)[0][0]
        actions.append({"type":"content","priority":"high","title":"Create a follow-up theme","detail":f"Make another video around '{theme}', while changing the opening or presentation.","evidence":"theme appears across your highest-viewed videos"})
    if interactions < max(1, views // 50):
        actions.append({"type":"engagement","priority":"medium","title":"Strengthen the interaction prompt","detail":"Ask one simple question or invite a specific opinion in the caption or ending.","evidence":"observed interaction volume relative to views"})
    if not actions:
        actions.append({"type":"consistency","priority":"medium","title":"Keep collecting performance data","detail":"Publish consistently so REelo can identify stronger themes and posting windows.","evidence":"limited observed performance history"})

    weekly_plan = [
        {"day":"Mon","focus":"Hook experiment","task":"Test a new first 2–3 seconds while keeping the topic familiar."},
        {"day":"Tue","focus":"Proven theme","task":"Publish a follow-up to a theme that already generated views."},
        {"day":"Wed","focus":"Community","task":"Create a reply-style or question-led post to encourage comments."},
        {"day":"Thu","focus":"Format test","task":"Reuse a strong format with a different angle or example."},
        {"day":"Fri","focus":"Best window","task":"Post in your strongest observed time window when practical."},
        {"day":"Sat","focus":"Experiment review","task":"Compare the week's posts and keep the strongest pattern."},
        {"day":"Sun","focus":"Plan next week","task":"Choose one proven theme and one controlled experiment for next week."},
    ]

    milestones = [
        {"name":"First growth target","condition":"Complete at least one weekly goal"},
        {"name":"Consistency streak","condition":"Publish on 3 or more planned days"},
        {"name":"Content winner","condition":"A new post enters your top 5 by observed views"},
    ]

    return {
        "goals": targets,
        "progress": progress,
        "actions": actions,
        "weekly_plan": weekly_plan,
        "milestones": milestones,
        "strongest_windows":[{"weekday":int(r["weekday"]),"hour":int(r["hour"]),"label":format_hour(r["hour"]),"views":int(r["views"] or 0),"interactions":int(r["interactions"] or 0)} for r in top_times],
        "note":"Growth guidance is based on your recorded REelo performance. It does not guarantee future growth or invent predictive metrics."
    }


@router.put("/goals")
def update_goals(weekly_views:int=0, weekly_followers:int=0, weekly_interactions:int=0, authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization)
    values = [max(0, min(int(x), 10_000_000)) for x in (weekly_views, weekly_followers, weekly_interactions)]
    with db() as c:
        ensure_table(c)
        c.execute("""
            INSERT INTO creator_growth_goals(creator_id,weekly_views,weekly_followers,weekly_interactions,updated_at)
            VALUES(?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(creator_id) DO UPDATE SET
                weekly_views=excluded.weekly_views,
                weekly_followers=excluded.weekly_followers,
                weekly_interactions=excluded.weekly_interactions,
                updated_at=CURRENT_TIMESTAMP
        """, (uid, *values))
    return {"saved": True, "goals":{"weekly_views":values[0],"weekly_followers":values[1],"weekly_interactions":values[2]}}
