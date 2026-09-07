from fastapi import APIRouter, Header, HTTPException
from main import db, current_user

router = APIRouter(prefix="/api/monetization", tags=["monetization"])


def ensure_monetization_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS creator_earnings(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,video_id TEXT,amount_cents INTEGER NOT NULL DEFAULT 0,source TEXT NOT NULL DEFAULT 'video_revenue',created_at TEXT DEFAULT CURRENT_TIMESTAMP)")


def build_dashboard(c, uid):
    ensure_monetization_table(c)
    user = c.execute("SELECT followers FROM users WHERE id=?", (uid,)).fetchone()
    totals = c.execute("SELECT COALESCE(SUM(amount_cents),0) earnings_cents,COUNT(*) payouts FROM creator_earnings WHERE user_id=?", (uid,)).fetchone()
    video_stats = c.execute("SELECT COALESCE(SUM(views),0) views,COALESCE(SUM(likes),0) likes,COALESCE(SUM(comments),0) comments FROM videos WHERE user_id=? AND status='ready'", (uid,)).fetchone()
    # Eligibility is deliberately transparent and configurable instead of pretending payments are live.
    followers = int(user['followers'] or 0)
    views = int(video_stats['views'] or 0)
    requirements = {'followers': 1000, 'views': 10000}
    eligible = followers >= requirements['followers'] and views >= requirements['views']
    return {
        'eligible': eligible,
        'requirements': requirements,
        'progress': {'followers': followers, 'views': views},
        'earnings_cents': int(totals['earnings_cents'] or 0),
        'earnings': round(int(totals['earnings_cents'] or 0) / 100, 2),
        'payouts': int(totals['payouts'] or 0),
        'stats': dict(video_stats),
        'note': 'Revenue is tracked internally. Connect a real payment provider before enabling withdrawals.'
    }


@router.get('/dashboard')
def dashboard(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, 'Login required')
    with db() as c:
        return build_dashboard(c, uid)


@router.get('/earnings')
def earnings(limit: int = 50, offset: int = 0, authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, 'Login required')
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    with db() as c:
        ensure_monetization_table(c)
        rows = c.execute('SELECT id,video_id,amount_cents,source,created_at FROM creator_earnings WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?', (uid, limit, offset)).fetchall()
        total = c.execute('SELECT COUNT(*) FROM creator_earnings WHERE user_id=?', (uid,)).fetchone()[0]
    return {'items': [dict(r) for r in rows], 'total': total, 'limit': limit, 'offset': offset}
