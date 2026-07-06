# 执行计划 - M1-1 项目脚手架

## 执行清单

- [x] 1. 创建后端项目结构 `backend/app/` 及子目录（core / models / schemas / api / collector / pipeline / analytics / ml）
- [x] 2. 编写 `backend/requirements.txt` 和 `backend/requirements-dev.txt`
- [x] 3. 实现 `backend/app/core/config.py`（pydantic-settings）
- [x] 4. 实现 `backend/app/core/database.py`（async SQLAlchemy 会话）
- [x] 5. 实现 `backend/app/core/cache.py`（Redis 客户端）
- [x] 6. 实现 `backend/app/main.py`（FastAPI 入口 + /health + CORS）
- [x] 7. 编写 `backend/Dockerfile`
- [x] 8. 初始化前端项目 `frontend/`（Vue3 + Vite + TS）
- [x] 9. 安装前端依赖（element-plus / echarts / pinia / vue-router / axios）
- [x] 10. 配置 `vite.config.ts`（API 代理）
- [x] 11. 编写 `frontend/Dockerfile`
- [x] 12. 编写 `docker-compose.yml`
- [x] 13. 编写 `.env.example`
- [x] 14. 更新 `.gitignore`
- [x] 15. 验证：后端 /health 返回 ok + /api/v1/ 返回正确 + 前端 200（Docker daemon 未运行，已用本地启动验证）

## 校验结果

```
GET /health           → {"status": "ok"}
GET /api/v1/          → {"message": "城市房价分析系统 API v1"}
GET localhost:5173    → 200, Content-Length: 397
vue-tsc --build       → 通过
vite build            → 通过
docker compose config → 语法正确
```
