# 执行计划 - 基础设施现代化

## 步骤

- [ ] 1. 创建 `backend/pyproject.toml`，从 requirements.txt 迁移所有依赖，分 main / dev 组
- [ ] 2. 在 backend/ 下运行 `uv lock` 生成 lock 文件
- [ ] 3. 删除 `backend/requirements.txt` 和 `backend/requirements-dev.txt`
- [ ] 4. 更新 `backend/Dockerfile` 使用 uv 安装
- [ ] 5. 更新 `docker-compose.yml`：去 named volume，改 bind mount 到 `./data/`
- [ ] 6. 创建根目录 `.gitignore`（合并已有规则 + __pycache__ / .venv / data/ 等）
- [ ] 7. 从 git 中移除已跟踪的 __pycache__ 文件
- [ ] 8. 验证：`uv sync` 成功

## 验证命令

```bash
cd backend && uv sync
uv run python -c "import fastapi; print(fastapi.__version__)"
```
