"""管理端数据质量审计端点：跨源一致性报告 + 模型新鲜度。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.core.config import settings
from app.ml.train import ModelStore
from app.models.user import UserAccount
from app.schemas.data_quality import DataQualityReport
from app.services.data_quality import build_report

router = APIRouter(prefix="/admin/data-quality", tags=["admin"])


@router.get("/report", response_model=DataQualityReport)
async def get_data_quality_report(
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """产出跨源数据质量报告（即时计算，秒级；无缓存——重训/导入后立即反映）。"""
    return await build_report(db, ModelStore(settings.ml_model_dir))
