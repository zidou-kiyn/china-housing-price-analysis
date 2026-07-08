from fastapi import APIRouter

from app.api.v1.admin_collect import router as admin_collect_router
from app.api.v1.admin_data_quality import router as admin_data_quality_router
from app.api.v1.admin_jobs import router as admin_jobs_router
from app.api.v1.admin_settings import router as admin_settings_router
from app.api.v1.admin_users import router as admin_users_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.geo import admin_router as admin_geo_router
from app.api.v1.geo import public_router as geo_router
from app.api.v1.auth import router as auth_router
from app.api.v1.cities import router as cities_router
from app.api.v1.predictions import router as predictions_router
from app.api.v1.prices import router as prices_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(cities_router)
api_router.include_router(prices_router)
api_router.include_router(analytics_router)
api_router.include_router(predictions_router)
api_router.include_router(admin_users_router)
api_router.include_router(admin_collect_router)
api_router.include_router(admin_data_quality_router)
api_router.include_router(admin_jobs_router)
api_router.include_router(admin_settings_router)
api_router.include_router(admin_geo_router)
api_router.include_router(geo_router)


@api_router.get("/")
async def api_root():
    return {"message": "城市房价分析系统 API v1"}
