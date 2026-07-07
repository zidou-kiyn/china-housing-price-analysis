"""用户管理端点（admin）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.core.errors import ApiError
from app.models.user import UserAccount
from app.schemas.auth import RoleUpdateRequest, UserAdminOut, UserListResponse

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    total = (await db.execute(select(func.count(UserAccount.id)))).scalar_one()
    result = await db.execute(
        select(UserAccount)
        .order_by(UserAccount.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [UserAdminOut.model_validate(u) for u in result.scalars()]
    return UserListResponse(total=total, page=page, page_size=page_size, items=items)


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
