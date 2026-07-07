# 采集代理设置 — 技术设计

## 存储

`app_setting`：`key varchar(50) PK`、`value JSON`、`updated_at`。`crawler_proxy` 的 value：
`{"enabled": bool, "url": "http://user:pass@host:port"}`。

## 服务 `app/services/app_settings.py`

- `async get_setting(session, key) -> dict | None` / `async set_setting(session, key, value)`（upsert）。
- `get_proxy_url_sync() -> str | None`：用 `database_url_sync` 短连接读 `crawler_proxy`，
  enabled 且 url 非空才返回；异常静默返回 None（表未建/DB 不可达时采集退化为直连）。
  供同步 `CrawlerHttpClient` 构造时调用——每个采集任务新建 source→新建 client→读一次，
  改设置即时生效，无进程内缓存失效问题。

## http_client 注入

`CrawlerHttpClient.__init__(..., proxy: str | None | Literal[False] = None)`：
- `None`（默认）→ 自动读设置；`False` → 强制直连（geo/测试用）；字符串 → 显式指定。
- 生效方式：`self.session.proxies = {"http": url, "https": url}`。

## API `app/api/v1/admin_settings.py`

- GET/PUT `/admin/settings/proxy`、POST `/admin/settings/proxy/test`（schema 入 `app/schemas/settings.py`）。
- 脱敏：`urllib.parse` 解析后重组，password → `***`。
- test：`asyncio.to_thread(requests.get, ..., proxies=..., timeout=15)` 单次；异常归类为
  `{ok: false, error: "<类型: 信息>"}`。测试目标 `https://www.creprice.cn/rank/citySel.html`，带浏览器 UA。

## 前端

DataManageView 筛选栏下方加 `el-card`「采集代理」：`el-switch` + `el-input show-password` +
测试/保存按钮 + 测试结果行内展示。`api/admin.ts` 加 fetchProxySettings/saveProxySettings/testProxy。

## 回滚

revert 提交 + `alembic downgrade -1`（app_setting 表）。
