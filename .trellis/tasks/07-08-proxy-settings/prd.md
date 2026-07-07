# 管理端采集代理设置

## Goal

管理员可在前端配置数据采集用的 HTTP 代理（启用开关 + 代理 URL + 连通性测试），采集流量（creprice）经代理出口，规避源站 IP 限流。

## 背景（2026-07-08 用户确认）

- creprice 屏蔽境外 IP：用户自建 resin 代理（美国出口 208.69.78.116）实测代理本身可用（httpbin 200），但访问 creprice 超时 → **境外代理不可用于采集**。
- 用户另有 iproyal 国内 IP 代理，密钥不外传，由用户在页面自行填写 → 功能做成通用代理 URL 输入（`http://user:pass@host:port`）。

## Requirements

### 后端

- 新表 `app_setting(key PK, value JSON, updated_at)`（Alembic 003，通用 KV，本次仅用 `crawler_proxy`）。
- `GET /admin/settings/proxy`：返回 `{enabled, url_masked, has_url}`，**密码永不回传明文**（`http://user:***@host:port`）。
- `PUT /admin/settings/proxy`：body `{enabled, url?}`；url 缺省时仅改开关（保留已存 URL），传空串清除；校验 URL 格式（http/https/socks5 + host:port）。
- `POST /admin/settings/proxy/test`：body `{url?}`（缺省用已存 URL），经该代理请求 creprice 城市页（单次、15s 超时、不重试），返回 `{ok, status_code, elapsed_ms, error}`。
- `CrawlerHttpClient` 支持代理：构造时未显式指定则自动读取 `crawler_proxy` 设置（启用且有 URL 才生效），改设置即时生效（每次采集任务新建 client）；**geo/DataV 下载不走代理**（直连无碍）。
- 全部端点 `require_admin`。

### 前端（DataManageView 内新增「采集代理」卡片）

- 启用开关、代理 URL 输入（show-password 隐藏密钥）、「测试连通」按钮（显示状态码/耗时/错误）、「保存」按钮。
- 已配置时显示脱敏 URL 占位提示；输入新值即覆盖。

## Constraints

- 代理 URL 含密钥，存 DB 不加密（本地单机部署可接受），但 API 响应与日志一律脱敏。
- 不做多代理池/轮换；单一代理配置。

## Acceptance Criteria

- [ ] 页面保存 resin 代理并测试：代理可达但 creprice 超时（错误信息可见）；关闭启用后采集恢复直连。
- [ ] 启用一个可用代理后触发采集，backend 请求经代理出口（打桩单测断言 session.proxies / 手动验证）。
- [ ] GET 响应中密码脱敏；PUT 仅改开关不丢已存 URL。
- [ ] 非 admin 访问设置端点 403。
- [ ] pytest 覆盖：KV 存取、脱敏、PUT 语义（仅开关/换 URL/清除）、test 端点（requests 打桩）、http_client 代理注入。
