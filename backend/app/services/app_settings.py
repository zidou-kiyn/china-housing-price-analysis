"""应用设置 KV 服务：异步读写 + 供同步采集客户端使用的代理读取。"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

PROXY_KEY = "crawler_proxy"


async def get_setting(session: AsyncSession, key: str) -> dict | None:
    row = await session.get(AppSetting, key)
    return row.value if row else None


async def set_setting(session: AsyncSession, key: str, value: dict) -> None:
    stmt = insert(AppSetting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"], set_={"value": stmt.excluded.value}
    )
    await session.execute(stmt)
    await session.commit()


def get_proxy_url_sync() -> str | None:
    """读取采集代理 URL（启用且非空才返回）；任何异常静默返回 None（退化为直连）。

    供同步 CrawlerHttpClient 构造时调用：每个采集任务新建 client 时读一次，
    改设置即时生效。短连接开销相对采集限速（秒级）可忽略。
    """
    try:
        engine = create_engine(settings.database_url_sync)
        try:
            with engine.connect() as conn:
                value = conn.execute(
                    select(AppSetting.value).where(AppSetting.key == PROXY_KEY)
                ).scalar_one_or_none()
        finally:
            engine.dispose()
    except Exception:
        logger.warning("读取采集代理设置失败，退化为直连", exc_info=True)
        return None

    if not value or not value.get("enabled"):
        return None
    url = (value.get("url") or "").strip()
    return url or None
