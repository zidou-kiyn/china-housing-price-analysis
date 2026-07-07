"""用户管理端点（admin）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.core.errors import ApiError
from app.models.user import UserAccount
from app.schemas.auth import (
    RoleUpdateRequest,
    StatusUpdateRequest,
    UserAdminOut,
    UserListResponse,
)

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=100),
    role: str | None = Query(None, pattern="^(user|admin)$"),
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    conditions = []
    if keyword:
        pattern = f"%{keyword}%"
        conditions.append(
            or_(UserAccount.username.ilike(pattern), UserAccount.email.ilike(pattern))
        )
    if role is not None:
        conditions.append(UserAccount.role == role)
    if is_active is not None:
        conditions.append(UserAccount.is_active == is_active)

    total = (
        await db.execute(select(func.count(UserAccount.id)).where(*conditions))
    ).scalar_one()
    result = await db.execute(
        select(UserAccount)
        .where(*conditions)
        .order_by(UserAccount.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [UserAdminOut.model_validate(u) for u in result.scalars()]
    return UserListResponse(total=total, page=page, page_size=page_size, items=items)


@router.patch("/{user_id}/status", response_model=UserAdminOut)
async def update_status(
    user_id: int,
    payload: StatusUpdateRequest,
    db: AsyncSession = Depends(get_session),
    admin: UserAccount = Depends(require_admin),
):
    user = await db.get(UserAccount, user_id)
    if user is None:
        raise ApiError(404, "用户不存在", "USER_NOT_FOUND")
    if user.id == admin.id:
        raise ApiError(400, "不能封禁/启用自己", "VALIDATION_ERROR")

    user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    admin: UserAccount = Depends(require_admin),
):
    user = await db.get(UserAccount, user_id)
    if user is None:
        raise ApiError(404, "用户不存在", "USER_NOT_FOUND")
    if user.id == admin.id:
        raise ApiError(400, "不能删除自己", "VALIDATION_ERROR")

    await db.delete(user)
    await db.commit()


@router.patch("/{user_id}/role", response_model=UserAdminOut)
async def update_role(
    user_id: int,
    payload: RoleUpdateRequest,
    db: AsyncSession = Depends(get_session),
    admin: UserAccount = Depends(require_admin),
):
    user = await db.get(UserAccount, user_id)
    if user is None:
        raise ApiError(404, "用户不存在", "USER_NOT_FOUND")
    if user.id == admin.id:
        raise ApiError(400, "不能修改自己的角色", "VALIDATION_ERROR")

    user.role = payload.role
    await db.commit()
    await db.refresh(user)
    return user
