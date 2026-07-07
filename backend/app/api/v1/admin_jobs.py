"""管理端后台任务查询端点（collect / geo_fetch / train 通用）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.core.errors import ApiError
from app.models.admin_job import AdminJob
from app.models.user import UserAccount
from app.schemas.admin_job import AdminJobListResponse, AdminJobOut

router = APIRouter(prefix="/admin/jobs", tags=["admin"])


@router.get("", response_model=AdminJobListResponse)
async def list_jobs(
    kind: str | None = Query(None, max_length=20),
    status: str | None = Query(None, pattern="^(pending|running|success|failed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    conditions = []
    if kind:
        conditions.append(AdminJob.kind == kind)
    if status:
        conditions.append(AdminJob.status == status)

    total = (
        await db.execute(select(func.count(AdminJob.id)).where(*conditions))
    ).scalar_one()
    rows = await db.execute(
        select(AdminJob)
        .where(*conditions)
        .order_by(AdminJob.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [AdminJobOut.model_validate(j) for j in rows.scalars()]
    return AdminJobListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/{job_id}", response_model=AdminJobOut)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    job = await db.get(AdminJob, job_id)
    if job is None:
        raise ApiError(404, "任务不存在", "JOB_NOT_FOUND")
    return job
