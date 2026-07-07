# compose 统一与端口收敛 — 技术设计

## 文件结构

```
docker-compose.yml            # 基准 = 生产安全配置（唯一被 prod 使用的文件）
docker-compose.override.yml   # dev 差异（docker compose up 时自动叠加）
.env                          # dev 环境变量（compose 内网地址，新建，git 忽略与否沿用现有约定）
.env.prod                     # 生产环境变量（保留现状）
```

- 生产：`docker compose -f docker-compose.yml --env-file .env.prod up -d --build`
- 开发：`docker compose up -d`（Docker Compose 默认自动叠加 override 文件）

## 基准 docker-compose.yml（生产形态）

- postgres/redis：无 `ports`；卷 `./data/postgres`、`./data/redis`；healthcheck 与 restart: unless-stopped 沿用现 prod 文件。
- backend：无 `ports`；`alembic upgrade head && uvicorn --workers 2`；`env_file: .env.prod`；healthcheck 沿用现 prod。
- frontend：`Dockerfile.prod`（nginx），`ports: ["8080:80"]`；nginx 已有 `/api` 反代到 backend（需核实 nginx.conf，geo 改走 API 后无额外静态目录需求）。
- 删除顶层 `volumes:` 命名卷段与 `name: housing-price-prod`。

## override（dev 形态）

- backend：覆盖 `command` 为 `--reload`（单进程）、`env_file: .env`、挂载 `./backend:/app`、去掉 restart。
- frontend：覆盖为 dev 镜像（现 `./frontend` Dockerfile）+ `npm run dev -- --host 0.0.0.0`、`ports: ["5173:5173"]`、挂载源码 + 匿名卷 `/app/node_modules`、环境变量 `VITE_PROXY_TARGET=http://backend:8000`。
- postgres/redis：无需覆盖（基准已是无端口 + `./` 卷）。

## 关键适配点

1. **Vite 代理**（frontend/vite.config.ts）：`target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000'`——容器内走 `backend:8000`，宿主机直跑（应急场景）仍默认 localhost。
2. **dev `.env` 新建**：`DATABASE_URL=...@postgres:5432/...`、`REDIS_URL=redis://redis:6379/0` 等（照 `.env.prod` 的内网写法，密钥用 dev 值）；提供 `.env.example`。
3. **数据迁移**：现 dev 数据已在 `./data/postgres`（dev compose 本来就是 `./` 卷），无需迁移；prod 命名卷数据为演示数据，直接废弃（如需保留，`docker run --rm -v pg_data_prod:/from -v ./data/postgres:/to alpine cp -a` 手工搬运，不在本任务范围）。
4. **prod workers=2 与后台任务**：保持 workers=2；后续任务机制以 DB 为状态源，与多 worker 兼容（见 admin-data-collect design）。
5. **文档**：`docs/` 部署文档全部命令替换；E2E/压测执行方式注明（E2E 打 5173 前端即可；loadtest.py 改经前端代理或 exec 进容器跑）。

## 回滚

单 commit 完成 compose 结构变更；回滚 = revert 该 commit（`./data/` 数据目录不受影响）。

## 风险

- E2E 或某些脚本可能硬编码 `localhost:8000` 直连后端——实现时先 `git grep -n "localhost:8000"` 全量排查并逐个改造。
- 首次 `docker compose up` 需构建 backend/frontend dev 镜像，node_modules 匿名卷首启较慢，属预期。
