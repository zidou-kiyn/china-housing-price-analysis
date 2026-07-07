# compose 统一与端口收敛 — 执行计划

## Part 1：compose 结构变更 + env（可独立提交）

- [ ] 重写 `docker-compose.yml` 为生产基准：postgres/redis/backend 无 `ports`，卷 `./data/postgres`、`./data/redis`，backend 挂 `./data/backend:/app/data`（为 geo 服务化预留，见 admin-data-collect design），`alembic upgrade head && uvicorn --workers 2`、healthcheck、restart，frontend 用 `Dockerfile.prod` + `8080:80`
- [ ] 新建 `docker-compose.override.yml`：backend `--reload` + `.env` + 源码挂载；frontend dev 镜像 + 5173 + `VITE_PROXY_TARGET=http://backend:8000`
- [ ] 删除 `docker-compose.prod.yml`；删除命名卷与 `name: housing-price-prod`
- [ ] 本地创建 dev `.env`（`.env.example` 已是内网写法，直接复制）
- 验证：`docker compose config` 两种形态语法正确；`git grep "5432:5432\|6379:6379\|8000:8000"` compose 无结果

## Part 2：脚本与前端适配（可独立提交）

- [ ] `frontend/vite.config.ts`：proxy target 改 `process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000'`；处理遗留 `vite.config.js`（Vite 优先加载 .js，确认后删除）
- [ ] `frontend/e2e/helpers.ts`：API_BASE 默认改走前端代理 `http://localhost:5173/api/v1`（保留 E2E_API_BASE 覆盖）
- [ ] `backend/scripts/loadtest.py`：确认 `docker compose exec backend` 下可跑（容器内 localhost:8000 可用），必要时文档注明
- 验证：`docker compose up -d` 全栈启动，5173 登录/图表正常；`docker compose exec backend uv run pytest` 通过

## Part 3：文档与收尾（可独立提交）

- [ ] `docs/09-工程规范与部署.md`（及 README 如涉及）：dev/prod 启动命令、exec 执行脚本与 pytest 方式、dev/prod 不能同时运行说明、`.env` 与 `.env.prod` 关系
- [ ] 生产形态验证：`docker compose -f docker-compose.yml --env-file .env.prod up -d --build`，8080 可用，`docker compose ps` 无 5432/6379/8000 映射
- [ ] E2E：`cd frontend && npm run test:e2e` 通过
- [ ] 更新 memory `dev-env-state.md`（服务启动方式已变）

## 完成门槛

- [ ] prd.md 验收标准逐条勾验
- [ ] 后端全量 pytest + 前端 lint/type-check/e2e 全绿
