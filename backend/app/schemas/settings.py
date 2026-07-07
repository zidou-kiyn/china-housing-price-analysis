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
