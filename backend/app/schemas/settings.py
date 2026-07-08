"""管理端设置相关 schema。"""

from pydantic import BaseModel, Field


class ProxySettingOut(BaseModel):
    enabled: bool
    url_masked: str | None  # http://user:***@host:port，密码永不回传
    has_url: bool


class ProxySettingUpdate(BaseModel):
    enabled: bool
    # None = 保留已存 URL；空串 = 清除；非空 = 覆盖
    url: str | None = Field(None, max_length=500)


class ProxyTestRequest(BaseModel):
    # None = 使用已保存的 URL
    url: str | None = Field(None, max_length=500)


class ProxyTestResult(BaseModel):
    ok: bool
    status_code: int | None = None
    elapsed_ms: int | None = None
    error: str | None = None


class CollectScheduleOut(BaseModel):
    """定时采集配置 + 调度器运行状态摘要。"""

    enabled: bool
    time: str  # "HH:MM"，容器本地时区
    batch: int
    # 调度器写入：last_run_date/last_run_at/last_job_id/last_result/
    # last_error/expand_cursor（自由结构，前端按需取用）
    state: dict | None


class CollectScheduleUpdate(BaseModel):
    enabled: bool
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    batch: int = Field(ge=1, le=20)
