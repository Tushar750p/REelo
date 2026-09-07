from main import app
from recommendation_api import router as recommendation_router

app.include_router(recommendation_router)
