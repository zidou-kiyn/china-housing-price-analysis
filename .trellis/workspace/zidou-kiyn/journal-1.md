# Journal - zidou-kiyn (Part 1)

> AI development session journal
> Started: 2026-07-06

---


## 2026-07-07 · 07-07-compose-unify 完成

- compose 收敛为基准（生产安全）+ override（dev 差异），DB/Redis/backend 全形态不暴露宿主机端口，卷统一 `./data/`；dev 全容器化，脚本/pytest 改 `docker compose exec backend` 执行。
- 踩坑记录：① override 对 `ports`/`env_file` 是合并语义，需 `!override` 标签（Compose ≥2.24.4）；② dev 源码挂载会遮蔽镜像 `.venv`，用匿名卷 `/app/.venv` 保护；③ dev/prod 共享 frontend 镜像 tag 会互相覆盖（nginx 镜像跑 npm 崩溃），已显式区分 `housing-price-frontend:dev|prod`；④ `vue-tsc --build` 因 tsconfig.node 缺 `noEmit` 会发射 `vite.config.js`（Vite 加载优先级高于 .ts），这是当初遗留文件的根因，已修。
- 遗留问题（不属本任务）：`npm run lint` 是脚手架死脚本，eslint 从未进依赖；宿主机曾遗留旧会话 vite/uvicorn 进程占端口，已清理。
- 验收全过：pytest 159 passed（容器内）、E2E 6 passed、prod 8080 与 dev 5173 双形态验证。

## 2026-07-07 · 07-07-admin-user-mgmt 完成

- 后端：/admin/users 增加 keyword/role/is_active 筛选；新增 status 切换与硬删除端点，自我操作返回 400；12 个 pytest 用例。
- 前端：UserManageView 加筛选栏与封禁/启用/删除操作列，自己行禁用；Playwright MCP 浏览器实测全流程通过（el-button 用原生 click 绕合成事件坑，见 memory）。
- 全量回归：pytest 171 passed，E2E 6 passed。
