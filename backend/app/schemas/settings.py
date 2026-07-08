"""管理端设置相关 schema。"""

from pydantic import BaseModel, Field


class ProxySettingOut(BaseModel):
    enabled: bool
    url_masked: str | None
    has_url: bool


class ProxySettingUpdate(BaseModel):
    enabled: bool
    url: str | None = Field(None, max_length=500)


class ProxyTestRequest(BaseModel):
    url: str | None = Field(None, max_length=500)


class ProxyTestResult(BaseModel):
    ok: bool
    status_code: int | None = None
    elapsed_ms: int | None = None
    error: str | None = None
