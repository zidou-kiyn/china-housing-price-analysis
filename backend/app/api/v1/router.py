from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/")
async def api_root():
    return {"message": "城市房价分析系统 API v1"}
