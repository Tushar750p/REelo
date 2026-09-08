from fastapi import Header, HTTPException

from main import app, feed as legacy_feed, db, current_user
from recommendation_api import router as recommendation_router, recommendations
from recommendation_feedback_api import router as recommendation_feedback_router
from profile_api import router as profile_router
from messaging_api import router as messaging_router
from stories_api import router as stories_router
from remix_api import router as remix_router
from sounds_api import router as sounds_router
from editor_api import router as editor_router
from drafts_api import router as drafts_router
from live_api import router as live_router
from live_ws import router as live_ws_router
from livekit_api import router as livekit_router
from live_guests_api import router as live_guests_router
from live_moderation_api import router as live_moderation_router
from moderation_api import router as moderation_router
from creator_api import router as creator_router
from monetization_api import router as monetization_router
from payouts_api import router as payouts_router
from admin_payouts_api import router as admin_payouts_router
from admin_moderation_api import router as admin_moderation_router
from community_actions_api import router as community_actions_router, blocked_ids
from trending_api import router as trending_router
from topics_api import router as topics_router
from smart_search_api import router as smart_search_router
from security import install_security
from payout_state import normalize_state, can_transition

app.router.routes[:] = [route for route in app.router.routes if not (getattr(route, "path", None) == "/api/feed" and "GET" in getattr(route, "methods", set()))]

def filter_blocked(result, authorization):
    uid=current_user(authorization)
    if not uid or not isinstance(result,dict) or not isinstance(result.get("items"),list): return result
    with db() as c: blocked=blocked_ids(c,uid)
    if not blocked:return result
    result["items"]=[item for item in result["items"] if str(item.get("user_id","")) not in blocked]
    return result

@app.get("/api/feed")
def personalized_feed(limit:int=20,following:bool=False,mode:str|None=None,authorization:str|None=Header(default=None)):
    if mode is not None: following=mode.strip().lower()=="following"
    result=legacy_feed(limit=limit,following=True,mode="following",authorization=authorization) if following else recommendations(limit=limit,authorization=authorization)
    return filter_blocked(result,authorization)

app.include_router(recommendation_router)
app.include_router(recommendation_feedback_router)
app.include_router(profile_router)
app.include_router(messaging_router)
app.include_router(stories_router)
app.include_router(remix_router)
app.include_router(sounds_router)
app.include_router(editor_router)
app.include_router(drafts_router)
app.include_router(live_router)
app.include_router(live_ws_router)
app.include_router(livekit_router)
app.include_router(live_guests_router)
app.include_router(live_moderation_router)
app.include_router(trending_router)
app.include_router(topics_router)
app.include_router(smart_search_router)
app.include_router(moderation_router)
app.include_router(creator_router)
app.include_router(monetization_router)
app.include_router(payouts_router)
app.include_router(admin_payouts_router)
app.include_router(admin_moderation_router)
app.include_router(community_actions_router)
install_security(app)

def validate_payout_transition(current:str,target:str)->str:
    current_state=normalize_state(current);target_state=normalize_state(target)
    if not can_transition(current_state,target_state):raise HTTPException(409,f"Invalid payout transition: {current_state} -> {target_state}")
    return target_state
