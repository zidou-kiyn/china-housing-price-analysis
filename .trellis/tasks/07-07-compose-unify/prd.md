# compose 统一与端口收敛

## Goal

合并 dev/prod 两份 compose 为「基准 + override」结构，postgres/redis/backend 不再暴露任何宿主机端口，数据卷统一使用 `./` 相对目录，dev 工作流全容器化。

## Requirements

- postgres、redis、backend 三个服务在 dev 与 prod 下都**不映射任何宿主机端口**（`ports` 段整体删除），服务间通过 compose 内网服务名互访。
- 仅 frontend 暴露端口：dev 5173（Vite），prod 8080（nginx）。
- 所有持久化卷改为 `./` 相对目录（postgres → `./data/postgres`，redis → `./data/redis`），删除命名卷 `pg_data_prod` / `redis_data_prod`。
- 合并为一份基准 `docker-compose.yml`（生产安全配置：不 reload、nginx 前端、restart 策略、healthcheck）+ `docker-compose.override.yml`（dev 差异：源码挂载、`--reload`、Vite dev server），删除 `docker-compose.prod.yml`。
- dev 全容器化后原宿主机工作流的替代路径必须可用并写入文档：
  - 后端脚本（create_admin / run_pipeline / fetch_geo）与 pytest 通过 `docker compose exec backend ...` 执行；
  - Vite 代理目标改为可配置（容器内指向 `http://backend:8000`，同时保留宿主机直跑的默认值）；
  - E2E（Playwright，baseURL localhost:5173）与压测脚本在新方式下可运行。
- 根目录提供 dev 用 `.env`（compose 内网地址），与 `.env.prod` 的关系在部署文档中说明；更新 `docs/` 部署文档中所有受影响的命令。

## Constraints

- 合并后 dev 与 prod 共用 `./data/` 目录，两套栈不能同时运行（原 `housing-price-prod` 独立项目名隔离方式随 prod 文件一起废弃）；此变化需在部署文档中显式注明。
- 现有 `./data/postgres` 中的 dev 数据不能丢。

## Acceptance Criteria

- [ ] `docker compose up -d` 起完整 dev 栈，前端 http://localhost:5173 可用、登录与图表正常（数据经 Vite 代理 → 容器内 backend）。
- [ ] `docker compose -f docker-compose.yml up -d --build` 起生产栈，http://localhost:8080 可用。
- [ ] 两种方式下 `docker compose ps` 均确认 postgres/redis/backend 无宿主机端口映射；宿主机 `curl localhost:8000` / `psql -h localhost` 连不通。
- [ ] `docker compose exec backend uv run pytest` 全部通过；`cd frontend && npm run test:e2e` 通过。
- [ ] `git grep -n "5432:5432\|6379:6379\|8000:8000"` 在 compose 文件中无结果；`docker-compose.prod.yml` 已删除，文档无残留引用。

## Notes

- 现状参考：dev 习惯是仅 `docker compose up -d postgres redis` + 宿主机 uvicorn/npm（见 memory dev-env-state），本任务会改变该工作流，完成后需更新该 memory。
