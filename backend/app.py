from fastapi import Header

from main import app, feed as legacy_feed
from recommendation_api import router as recommendation_router, recommendations
from moderation_api import router as moderation_router
from creator_api import router as creator_router
from security import install_security

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
install_security(app)
