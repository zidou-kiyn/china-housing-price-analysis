# M1 基础设施现代化 - uv 迁移 + Docker 改造 + 清理

## Goal

将后端 Python 项目管理从 requirements.txt 迁移到 uv（pyproject.toml + uv.lock），更新 Docker Compose 去掉 named volume 改用本地目录，清理 __pycache__ 并完善 .gitignore。确保 Windows 本地开发和 Linux Docker 部署两条路径都能正常工作。

## Requirements

- 后端从 `requirements.txt` / `requirements-dev.txt` 迁移到 `pyproject.toml` + `uv.lock`
- Docker Compose 去掉 `volumes: pgdata` named volume，数据持久化改为 `./data/postgres` bind mount
- Docker Compose 中 Redis 数据也用本地目录 `./data/redis`
- 更新 backend Dockerfile 使用 uv 安装依赖
- 清理已提交的 `__pycache__` 目录
- 完善 `.gitignore`（__pycache__、.venv、data/、node_modules 等）
- 删除旧的 `requirements.txt` 和 `requirements-dev.txt`

## Constraints

- Windows 环境无法使用 Docker，本地用 `uv sync` + 直接运行
- Docker 配置保留供 Linux 环境使用
- 不改变现有代码逻辑，仅改构建/环境管理

## Acceptance Criteria

- [ ] `backend/pyproject.toml` 存在且包含所有依赖
- [ ] `backend/uv.lock` 存在
- [ ] `backend/requirements.txt` 和 `requirements-dev.txt` 已删除
- [ ] `backend/Dockerfile` 使用 uv 安装依赖
- [ ] `docker-compose.yml` 无 named volume，数据目录为 `./data/`
- [ ] `.gitignore` 覆盖 __pycache__、.venv、data/、node_modules
- [ ] git 中无 __pycache__ 文件
- [ ] `uv sync` 可成功安装所有依赖（Windows 验证）
