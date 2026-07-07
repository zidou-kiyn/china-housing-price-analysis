# M2-4 技术设计

## 后端

### 模块划分

| 文件 | 职责 |
|------|------|
| `app/core/security.py` | `hash_password`/`verify_password`（passlib bcrypt）、`create_access_token`/`decode_access_token`（python-jose，HS256，`sub`=user_id，`exp` 按 settings） |
| `app/core/errors.py` | `ApiError(HTTPException)` 携带 `code`；`register_exception_handlers(app)` 渲染 `{"detail", "code"}` |
| `app/schemas/auth.py` | `RegisterRequest`（username 3~50、email EmailStr、password ≥6）、`LoginRequest`、`TokenResponse`、`UserOut`、`UserAdminOut`（含 is_active/created_at）、`RoleUpdateRequest` |
| `app/api/v1/auth.py` | register/login/me 三端点 |
| `app/api/v1/admin_users.py` | `GET /admin/users`、`PATCH /admin/users/{id}/role` |
| `app/api/deps.py` | `get_current_user`、`require_user`、`require_admin` |

### 鉴权流

- 凭证传递用 `HTTPBearer(auto_error=False)`；缺失/格式错 → 401 `TOKEN_INVALID`。
- `decode_access_token`：`jose.ExpiredSignatureError` → 401 `TOKEN_EXPIRED`；其他 JWTError → 401 `TOKEN_INVALID`。
- 用户加载：`sub` 不存在 → 401 `TOKEN_INVALID`；`is_active=False` → 403 `PERMISSION_DENIED`。
- `require_user = Depends(get_current_user)`（任何已登录用户）；`require_admin` 在其上校验 `role == "admin"`。

### 错误码兼容策略

`ApiError` 继承 `HTTPException` 并附加 `code`；专属 handler 输出 `{"detail": msg, "code": code}`。既有端点继续抛原生 `HTTPException`（响应仍为 `{"detail": msg}`），互不影响。

### 收权点

`analytics.py` 中 `price_compare`、`map_heat` 增加 `user: UserAccount = Depends(require_user)`。`/rank` 保持公开。

### email 校验依赖

`EmailStr` 需要 `email-validator`，pydantic v2 下随 `pydantic[email]` 提供 —— pyproject 增加 `email-validator`。

## 前端

### auth store（Pinia）

- state：`token`（localStorage 恢复）、`user`。
- actions：`login(username, password)` → 存 token → `fetchMe()`；`register(...)` → 成功后调 `login`；`fetchMe()`；`logout()`。
- App 启动时（router 守卫首跳）若有 token 无 user → `fetchMe()`，401 由拦截器清 token。

### 路由守卫

```
/compare, /map           meta: { requiresAuth: true }
/admin/users             meta: { requiresAuth: true, requiresAdmin: true }
```

`router.beforeEach`：requiresAuth 且未登录 → `/login?redirect=to.fullPath`；requiresAdmin 且 role !== 'admin' → `/`。守卫为 async：有 token 无 user 时先 await fetchMe（失败视为未登录）。

### 页面

- LoginView/RegisterView：居中卡片表单（el-form + rules 校验），错误用 ElMessage 显示后端 detail。
- UserManageView：el-table（id/用户名/邮箱/角色/状态/注册时间）+ 角色列内联 el-select 触发 PATCH。
- AppHeader：右侧 `el-dropdown`（用户名 → 用户管理[admin]/退出登录）或「登录 / 注册」链接组。

## 测试策略

- `tests/api/test_auth.py`：注册成功/重复 409、登录成功/失败 401、me 有/无 token、admin 端点 403/200、角色修改。fixture 生成随机后缀用户并在 teardown 删除（直连 DB delete）。
- `test_analytics.py`：新增模块级 `auth_headers` fixture（注册+登录临时用户），compare/map 用例带 headers；新增无 token 401 用例。
