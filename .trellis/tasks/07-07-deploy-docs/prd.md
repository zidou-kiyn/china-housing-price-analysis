# M3-4 生产部署配置与文档

## Goal

交付可一键启动的生产部署形态：前端 nginx 静态服务 + API 反代，后端多 worker + 启动自动迁移，`docker compose -f docker-compose.prod.yml up` 可运行；同步更新 docs/09 部署章节。

## Requirements

- `frontend/Dockerfile.prod`：多阶段构建（node build → nginx:alpine 托管 dist），`frontend/nginx.conf`：SPA fallback + `/api/` 反代 backend:8000。
- 后端复用现有镜像，prod compose 覆盖 command：`alembic upgrade head && uvicorn --workers 2`（不挂代码卷、不 reload）。
- `docker-compose.prod.yml`：postgres/redis 用独立命名卷、不对外发布端口；backend 仅内网；frontend 发布 8080:80；全服务 healthcheck + restart: unless-stopped。
- `.env.prod.example`：DATABASE_URL/REDIS_URL（服务名寻址）、JWT_SECRET_KEY、APP_ENV=production、LOG_LEVEL。
- docs/09 §4.4 用真实文件与命令替换占位描述（含首次初始化：种子 admin、跑管线采数）。
- 与 dev 栈可并存（无端口/卷冲突）。

## Acceptance Criteria

- [x] docker compose -f docker-compose.prod.yml build 成功
- [x] up 后 frontend http://localhost:8080 可访问、/api 反代可用、backend /health ok
- [x] 数据库 schema 由启动迁移自动建好
- [x] docs/09 §4.4 更新为实际配置
