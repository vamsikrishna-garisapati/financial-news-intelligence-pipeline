"""API routers."""

from fastapi import APIRouter

from app.api.routes import analytics, collection_runs, companies, health, news

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(collection_runs.router, tags=["collection-runs"])
api_router.include_router(news.router, tags=["news"])
api_router.include_router(companies.router, tags=["companies"])
api_router.include_router(analytics.router, tags=["analytics"])
