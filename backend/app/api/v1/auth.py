"""注册 / 登录 / 当前用户端点。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.core.errors import ApiError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import UserAccount
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_session)):
    existing = (
        await db.execute(select(UserAccount).where(UserAccount.username == payload.username))
    ).scalar_one_or_none()
    if existing:
        raise ApiError(409, "用户名已存在", "USERNAME_EXISTS")

    existing = (
        await db.execute(select(UserAccount).where(UserAccount.email == payload.email))
    ).scalar_one_or_none()
    if existing:
        raise ApiError(409, "邮箱已存在", "EMAIL_EXISTS")

    user = UserAccount(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_session)):
    user = (
        await db.execute(select(UserAccount).where(UserAccount.username == payload.username))
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(401, "用户名或密码错误", "INVALID_CREDENTIALS")
    if not user.is_active:
        raise ApiError(403, "账号已被禁用", "PERMISSION_DENIED")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: UserAccount = Depends(get_current_user)):
    return user
