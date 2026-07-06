# M1-1 项目脚手架

## Goal

搭建 backend（FastAPI）+ frontend（Vue3 + Vite）项目骨架，配置 Docker Compose 一键启动全栈环境（PostgreSQL + Redis + Backend + Frontend），并实现健康检查端点。

## Requirements

- **后端**：
  - Python 3.11 + FastAPI 项目结构（见 `docs/09-工程规范与部署.md` 目录结构）
  - `backend/app/main.py` 入口，挂载 `/api/v1` 路由前缀
  - `backend/app/core/config.py` 使用 pydantic-settings 读取 `.env`
  - `backend/app/core/database.py` 异步 SQLAlchemy 2.0 会话工厂
  - `backend/app/core/cache.py` Redis 客户端
  - `GET /health` 健康检查端点（返回 `{"status": "ok"}`）
  - `requirements.txt` 含全部后端依赖
  - `Dockerfile`

- **前端**：
  - Vue 3 + Vite + TypeScript 项目（`npm create vue@latest`）
  - 安装 Element Plus / ECharts / Pinia / Vue Router / axios
  - `vite.config.ts` 配置 `/api` 代理到后端
  - `Dockerfile`

- **Docker Compose**：
  - `docker-compose.yml`：postgres:16 / redis:7 / backend / frontend 四服务
  - `.env.example` 示例环境变量

- **工程配置**：
  - `.gitignore`（Python + Node + IDE + .env）
  - `backend/requirements-dev.txt`（ruff / mypy / pytest / httpx）

## Acceptance Criteria

- [ ] `docker-compose up` 四个服务全部启动无报错
- [ ] `curl http://localhost:8000/health` 返回 `{"status": "ok"}`
- [ ] `curl http://localhost:8000/api/v1/` 返回 FastAPI 根响应或 404（路由已挂载）
- [ ] `http://localhost:5173` 前端开发页面可访问
- [ ] 后端可连接 PostgreSQL 和 Redis（启动日志无连接错误）
- [ ] `.env.example` 包含所有必需的环境变量键

## Dependencies

无前置依赖（M1 首个任务）。

## Ordering

后续任务 `db-schema` 依赖本任务的项目结构和数据库连接配置。
