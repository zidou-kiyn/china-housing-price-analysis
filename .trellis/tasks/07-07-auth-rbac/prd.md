# M2-4 JWT 鉴权与角色权限

## Goal

实现 JWT 登录注册、guest/user/admin 三角色权限控制（后端依赖 + 前端路由守卫），并交付管理后台雏形（用户管理页）。

## Requirements

### 后端鉴权端点（docs/05 §3.1）

- `POST /auth/register`：请求 `{username, email, password}` → 201 `{id, username, email, role}`；用户名重复 409 `USERNAME_EXISTS`，邮箱重复 409 `EMAIL_EXISTS`。密码 bcrypt 哈希。
- `POST /auth/login`：请求 `{username, password}` → 200 `{access_token, token_type: "bearer"}`；失败 401 `INVALID_CREDENTIALS`。token 30 分钟过期（settings 已有配置）。
- `GET /auth/me`：Bearer token → `{id, username, email, role, is_active}`。

### 错误响应带错误码

- 鉴权相关错误响应格式为 `{"detail": "...", "code": "..."}`（docs/05 §4）：`INVALID_CREDENTIALS`、`TOKEN_EXPIRED`、`TOKEN_INVALID`、`PERMISSION_DENIED`、`USERNAME_EXISTS`、`EMAIL_EXISTS`。
- 通过自定义异常 + 全局 handler 实现，不改动既有端点的纯 `detail` 格式。

### 角色依赖与收权（docs/05 §2 权限矩阵）

- `get_current_user`（解析 Bearer → 加载用户，无效/过期 401，禁用用户 403）、`require_user`（登录即可）、`require_admin`（admin，否则 403 `PERMISSION_DENIED`）。
- 收权：`GET /compare`、`GET /map/heat` 需 user+；元数据/均价/走势/排行保持公开。
- 管理端点：`GET /admin/users`（分页用户列表）、`PATCH /admin/users/{id}/role`（改角色，取值 user|admin），均需 admin。

### 管理员种子

- `backend/scripts/create_admin.py`：命令行创建或提升 admin 账号（本地/部署初始化用）。

### 前端

- `api/auth.ts`（register/login/fetchMe）+ auth store 扩展（login/logout/fetchMe、启动时恢复会话）。
- LoginView（用户名+密码，成功后跳转 `redirect` 查询参数或首页）、RegisterView（用户名/邮箱/密码，成功后自动登录）。
- 路由守卫：`/compare`、`/map` 标记 `requiresAuth`，未登录跳 `/login?redirect=...`；`/admin/*` 标记 `requiresAdmin`，非 admin 跳首页。
- AppHeader 右侧用户区：未登录显示「登录 / 注册」；已登录显示用户名下拉（含退出登录，admin 额外显示「用户管理」入口）。
- UserManageView（`/admin/users`）：用户列表表格 + 角色下拉修改。

## 约束

- 测试更新：test_analytics.py 的 compare/map 用例需带 token；新增 test_auth.py 覆盖注册/登录/me/权限矩阵。
- 测试产生的用户数据须在用例内自清理（live dev DB）。
- 前端 401 拦截（已存在）保持跳登录页行为。

## Acceptance Criteria

- [ ] 注册 → 登录 → /auth/me 全链路通过；重复用户名/邮箱 409
- [ ] 无 token 访问 /compare、/map/heat 返回 401；user token 可访问
- [ ] 非 admin 访问 /admin/users 返回 403；admin 可列出用户并修改角色
- [ ] 前端未登录点「区域对比」跳登录页，登录后跳回原页面
- [ ] AppHeader 登录态切换正确；admin 可见用户管理入口
- [ ] 后端 pytest 全绿；前端 type-check/build 通过 + 浏览器实测
