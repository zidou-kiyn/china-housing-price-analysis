from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.core.source_policy import DEFAULT_SOURCE, REGISTERED_SOURCES
from app.models.user import UserAccount

_bearer = HTTPBearer(auto_error=False)


async def get_session(db: AsyncSession = Depends(get_db)) -> AsyncGenerator[AsyncSession, None]:
    yield db


def source_param(source: str = Query(DEFAULT_SOURCE)) -> str:
    """价格/分析端点的数据源参数校验：缺省 creprice，非登记源 422。

    creprice-first 源硬隔离：视图按单一 source 直读，杜绝跨源合并。取值域为
    已登记 price_snapshot 源（source_policy.REGISTERED_SOURCES）；NBS 指数不在此列
    （走 /prices/index/trend 独立路径）。
    """
    if source not in REGISTERED_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"未知数据源: {source}（可选 {', '.join(REGISTERED_SOURCES)}）",
        )
    return source


async def get_cache(cache: Redis = Depends(get_redis)) -> Redis:
    return cache


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserAccount:
    if credentials is None:
        raise ApiError(401, "未提供认证凭证", "TOKEN_INVALID")
    try:
        user_id = decode_access_token(credentials.credentials)
    except ExpiredSignatureError:
        raise ApiError(401, "Token 已过期", "TOKEN_EXPIRED")
    except (JWTError, KeyError, ValueError):
        raise ApiError(401, "Token 无效", "TOKEN_INVALID")

    user = await db.get(UserAccount, user_id)
    if user is None:
        raise ApiError(401, "Token 无效", "TOKEN_INVALID")
    if not user.is_active:
        raise ApiError(403, "账号已被禁用", "PERMISSION_DENIED")
    return user


async def require_user(user: UserAccount = Depends(get_current_user)) -> UserAccount:
    return user


async def require_admin(user: UserAccount = Depends(get_current_user)) -> UserAccount:
    if user.role != "admin":
        raise ApiError(403, "无权限访问", "PERMISSION_DENIED")
    return user
