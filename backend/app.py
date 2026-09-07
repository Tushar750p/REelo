from fastapi import Header, HTTPException

from main import app, feed as legacy_feed
from recommendation_api import router as recommendation_router, recommendations
from moderation_api import router as moderation_router
from creator_api import router as creator_router
from monetization_api import router as monetization_router
from payouts_api import router as payouts_router
from admin_payouts_api import router as admin_payouts_router
from admin_moderation_api import router as admin_moderation_router
from security import install_security
from payout_state import normalize_state, can_transition

# Replace the default chronological For You handler without modifying the large legacy file.
app.router.routes[:] = [
    route for route in app.router.routes
    if not (getattr(route, "path", None) == "/api/feed" and "GET" in getattr(route, "methods", set()))
]

@app.get("/api/feed")
def personalized_feed(
    limit: int = 20,
    following: bool = False,
    mode: str | None = None,
    authorization: str | None = Header(default=None),
):
    if mode is not None:
        following = mode.strip().lower() == "following"
    if following:
        return legacy_feed(limit=limit, following=True, mode="following", authorization=authorization)
    return recommendations(limit=limit, authorization=authorization)

app.include_router(recommendation_router)
app.include_router(moderation_router)
app.include_router(creator_router)
app.include_router(monetization_router)
app.include_router(payouts_router)
app.include_router(admin_payouts_router)
app.include_router(admin_moderation_router)
install_security(app)

# Internal lifecycle guard used by future admin/provider endpoints.
def validate_payout_transition(current: str, target: str) -> str:
    current_state = normalize_state(current)
    target_state = normalize_state(target)
    if not can_transition(current_state, target_state):
        raise HTTPException(409, f"Invalid payout transition: {current_state} -> {target_state}")
    return target_state
