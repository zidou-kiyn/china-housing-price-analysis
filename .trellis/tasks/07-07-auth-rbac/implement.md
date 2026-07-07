# M2-4 执行计划

## 后端

1. [ ] pyproject 增加 `email-validator`，同步 venv
2. [ ] `app/core/security.py`（密码哈希 + JWT 签发/解析）
3. [ ] `app/core/errors.py`（ApiError + handler，main.py 注册）
4. [ ] `app/schemas/auth.py`
5. [ ] `app/api/deps.py` 增加 get_current_user / require_user / require_admin
6. [ ] `app/api/v1/auth.py` + `app/api/v1/admin_users.py`，注册进 router
7. [ ] analytics.py compare/map 收权
8. [ ] `scripts/create_admin.py`
9. [ ] `tests/api/test_auth.py` + test_analytics.py 加 token
10. [ ] 验证：`pytest -m "not slow"`、`pytest tests/api -m slow`、ruff

## 前端

11. [ ] `api/auth.ts`、auth store 扩展
12. [ ] LoginView / RegisterView + 路由（/login /register）
13. [ ] 路由守卫（requiresAuth / requiresAdmin）
14. [ ] AppHeader 用户区
15. [ ] UserManageView + /admin/users 路由
16. [ ] 验证：type-check、build、浏览器实测（守卫跳转/登录/注册/用户管理/退出）

## 验证命令

```bash
cd backend && .venv/bin/python -m pytest -m "not slow" -q && .venv/bin/python -m pytest tests/api -m slow -q && .venv/bin/python -m ruff check app tests
cd frontend && npm run type-check && npm run build
```

## 回滚点

- 后端收权独立于鉴权端点：如前端联调受阻，可临时回退第 7 步单独提交。
