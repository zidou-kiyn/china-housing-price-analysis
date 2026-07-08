# GeoJSON 迁移至前端静态资源 — 执行计划

## 前置条件

- 07-08-backend-single-source 已完成（后端 geo 模块已删除）
- `data/geo/` 目录下的文件尚存（在 backend-single-source 删除前先复制）

**实际执行顺序调整**：由于 backend-single-source 会删除 `data/geo/`，本任务的文件复制步骤应在 backend-single-source 的 `rm -rf data/geo/` 之前执行，或从 Git 历史中恢复。建议在 backend-single-source 执行时，先完成本任务的文件复制。

## 步骤

### 1. 复制 GeoJSON 文件到前端

```bash
mkdir -p frontend/public/geo
cp data/geo/*.json frontend/public/geo/
ls frontend/public/geo/ | wc -l  # 预期 333
```

### 2. 修改 loadGeoJson()

编辑 `frontend/src/utils/geo.ts`：
- 将 axios API 调用改为 `fetch('/geo/${cityCode}.json')`
- 移除对后端 API 的 import

### 3. 清理前端 API 调用

编辑 `frontend/src/api/admin.ts`：
- 移除地图获取/爬取相关的 API 函数

### 4. 验证

```bash
# 启动前端 dev server
docker compose up -d frontend
# 打开任意城市分析页面，检查地图是否正常渲染
# 检查 Network 面板：地图请求应为 /geo/xxx.json（200），非 /api/v1/geo/xxx
```

- HeatMap.vue 正常渲染
- 浏览器 Network 面板显示直接请求静态文件
- 无 401/403 错误

### 5. Git 提交

```bash
git add frontend/public/geo/
# 单独提交 GeoJSON 文件（约 25MB）
```

## 回滚方案

- 删除 `frontend/public/geo/` 目录
- 恢复 `utils/geo.ts` 的 API 调用方式
- 恢复后端 geo 模块（从 Git 历史）
