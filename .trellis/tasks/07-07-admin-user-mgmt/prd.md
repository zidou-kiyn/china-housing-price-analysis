# 管理端用户管理完善

## Goal

在现有「用户列表 + 改角色」基础上，补齐封禁/启用、删除、搜索筛选能力，形成完整的用户管理闭环（前后端）。

## Requirements

### 后端（backend/app/api/v1/admin_users.py 扩展）

- `PATCH /admin/users/{id}/status`：切换 `is_active`（封禁/启用）。禁止操作自己。被封禁用户下次鉴权即 403（`get_current_user` 已校验 is_active，无需额外改动，验收时确认）。
- `DELETE /admin/users/{id}`：硬删除用户。禁止删除自己。
- `GET /admin/users` 增加查询参数：`keyword`（用户名/邮箱模糊匹配）、`role`、`is_active`，与现有分页组合。
- 所有端点 `require_admin`；schema 补充到 `backend/app/schemas/auth.py`。

### 前端（frontend/src/views/admin/UserManageView.vue 扩展）

- 表格上方：关键词搜索框 + 角色筛选 + 状态筛选，变更即刷新列表（重置到第 1 页）。
- 每行操作：封禁/启用按钮（按当前状态切换文案）、删除按钮（ElMessageBox 二次确认）。
- 对自己那一行禁用封禁与删除操作（与后端约束一致）。
- `frontend/src/api/admin.ts` 补充对应 API 封装与类型。

## Constraints

- 不做软删除/回收站；不做批量操作；不做管理员重置他人密码（超出本次范围）。
- 删除用户无需级联业务数据（用户表当前无业务外键关联，实现时用 `\d users` 或模型 relationship 核实一次）。

## Acceptance Criteria

- [ ] 封禁一个测试用户后，该用户携旧 token 访问任意需登录接口返回 403；启用后恢复正常。
- [ ] 管理员无法封禁/删除自己（后端 400/403，前端按钮禁用）。
- [ ] keyword/role/status 筛选组合查询结果正确，分页正常。
- [ ] 删除用户后列表刷新、总数减一，再次登录该账号提示凭证无效。
- [ ] 后端新增端点有对应 pytest 用例（成功 + 自我操作被拒 + 非 admin 403）。
