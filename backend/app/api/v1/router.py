from fastapi import APIRouter

from app.api.v1.analytics import router as analytics_router
from app.api.v1.cities import router as cities_router
from app.api.v1.prices import router as prices_router

api_router = APIRouter()
api_router.include_router(cities_router)
api_router.include_router(prices_router)
api_router.include_router(analytics_router)


@api_router.get("/")
async def api_root():
    return {"message": "城市房价分析系统 API v1"}
