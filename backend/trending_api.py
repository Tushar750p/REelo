from fastapi import APIRouter
from main import db
from trending import rank_trending

router=APIRouter(prefix='/api',tags=['trending'])

@router.get('/trending')
def trending(limit:int=20):
    limit=max(1,min(limit,50))
    with db() as c:
        rows=c.execute("SELECT v.*,u.username,u.display_name FROM videos v JOIN users u ON u.id=v.user_id WHERE v.status='ready' ORDER BY v.created_at DESC LIMIT 200").fetchall()
    items=rank_trending([dict(r) for r in rows],limit)
    return {'items':items,'algorithm':'trending-v1','limit':limit}
