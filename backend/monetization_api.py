from fastapi import APIRouter, Header, HTTPException
from main import db, current_user

router = APIRouter(prefix="/api/monetization", tags=["monetization"])

BASE_CPM_CENTS = 50
LIKE_BONUS_CENTS = 2
COMMENT_BONUS_CENTS = 5


def ensure_monetization_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS creator_earnings(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,video_id TEXT,amount_cents INTEGER NOT NULL DEFAULT 0,source TEXT NOT NULL DEFAULT 'video_revenue',created_at TEXT DEFAULT CURRENT_TIMESTAMP)")


def verification_status(c, uid):
    c.execute("CREATE TABLE IF NOT EXISTS creator_verifications(id TEXT PRIMARY KEY,user_id TEXT UNIQUE NOT NULL,legal_name TEXT NOT NULL,country TEXT NOT NULL DEFAULT 'IN',status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    row = c.execute("SELECT status FROM creator_verifications WHERE user_id=?", (uid,)).fetchone()
    return row['status'] if row else 'not_started'


def estimate_video_cents(views, likes, comments):
    qualified_views = max(0, int(views or 0))
    engagement = max(0, int(likes or 0)) * LIKE_BONUS_CENTS + max(0, int(comments or 0)) * COMMENT_BONUS_CENTS
    return (qualified_views * BASE_CPM_CENTS) // 1000 + engagement


def build_dashboard(c, uid):
    ensure_monetization_table(c)
    user = c.execute("SELECT followers FROM users WHERE id=?", (uid,)).fetchone()
    video_stats = c.execute("SELECT COALESCE(SUM(views),0) views,COALESCE(SUM(likes),0) likes,COALESCE(SUM(comments),0) comments FROM videos WHERE user_id=? AND status='ready'", (uid,)).fetchone()
    videos = c.execute("SELECT id,caption,views,likes,comments,created_at FROM videos WHERE user_id=? AND status='ready' ORDER BY created_at DESC LIMIT 100", (uid,)).fetchall()
    followers = int(user['followers'] or 0)
    views = int(video_stats['views'] or 0)
    requirements = {'followers': 1000, 'views': 10000}
    threshold_eligible = followers >= requirements['followers'] and views >= requirements['views']
    verification = verification_status(c, uid)
    eligible = threshold_eligible and verification == 'approved'
    estimated_cents = estimate_video_cents(views, video_stats['likes'], video_stats['comments']) if eligible else 0
    per_video = []
    for row in videos:
        item = dict(row)
        item['estimated_earnings_cents'] = estimate_video_cents(item['views'], item['likes'], item['comments']) if eligible else 0
        item['estimated_earnings'] = round(item['estimated_earnings_cents'] / 100, 2)
        per_video.append(item)
    totals = c.execute("SELECT COALESCE(SUM(amount_cents),0) earnings_cents,COUNT(*) payouts FROM creator_earnings WHERE user_id=?", (uid,)).fetchone()
    blockers = []
    if followers < requirements['followers']: blockers.append('Reach 1,000 followers')
    if views < requirements['views']: blockers.append('Reach 10,000 qualified views')
    if verification != 'approved': blockers.append('Complete creator verification')
    return {
        'eligible': eligible,
        'threshold_eligible': threshold_eligible,
        'verification_status': verification,
        'requirements': requirements,
        'progress': {'followers': followers, 'views': views},
        'blockers': blockers,
        'estimated_earnings_cents': estimated_cents,
        'estimated_earnings': round(estimated_cents / 100, 2),
        'recorded_earnings_cents': int(totals['earnings_cents'] or 0),
        'recorded_earnings': round(int(totals['earnings_cents'] or 0) / 100, 2),
        'payouts': int(totals['payouts'] or 0),
        'stats': dict(video_stats),
        'rate': {'cpm_cents': BASE_CPM_CENTS, 'like_bonus_cents': LIKE_BONUS_CENTS, 'comment_bonus_cents': COMMENT_BONUS_CENTS},
        'videos': per_video,
        'note': 'Estimated revenue only. Actual payouts require approved monetization policy, advertiser revenue and a connected payment provider.'
    }


@router.get('/dashboard')
def dashboard(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid: raise HTTPException(401, 'Login required')
    with db() as c:
        return build_dashboard(c, uid)


@router.get('/earnings')
def earnings(limit: int = 50, offset: int = 0, authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    if not uid: raise HTTPException(401, 'Login required')
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    with db() as c:
        ensure_monetization_table(c)
        rows = c.execute('SELECT id,video_id,amount_cents,source,created_at FROM creator_earnings WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?', (uid, limit, offset)).fetchall()
        total = c.execute('SELECT COUNT(*) FROM creator_earnings WHERE user_id=?', (uid,)).fetchone()[0]
    return {'items': [dict(r) for r in rows], 'total': total, 'limit': limit, 'offset': offset}
