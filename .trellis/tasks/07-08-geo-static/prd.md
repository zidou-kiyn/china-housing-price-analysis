# GeoJSON 迁移至前端静态资源

## Goal

将城市 GeoJSON 边界文件从后端运行时获取改为前端静态资源，提交到仓库，实现零后端依赖的地图加载。

## Dependencies

依赖 07-08-backend-single-source 完成（后端 geo 模块已删除）。

## Requirements

### 文件迁移
- 将 `data/geo/` 下全部 333 个 GeoJSON 文件移动到 `frontend/public/geo/`
- 文件名格式不变：`{city_code}.json`
- 文件内容不做精度压缩，保持原样
- 全部提交到 Git 仓库（约 25MB）

### 前端加载改造
- `frontend/src/utils/geo.ts` 的 `loadGeoJson(cityCode)` 函数：
  - 原来：调用后端 `GET /geo/{city_code}` API（需认证）
  - 改为：直接 `fetch('/geo/${cityCode}.json')`（无需认证）
- 内存缓存（`registeredMaps` Set）逻辑保持不变

### 删除
- `frontend/src/api/admin.ts` 中地图相关的 API 调用函数（如有）
- 后端 `data/geo/` 目录（由 backend-single-source 子任务处理）

## Acceptance Criteria

- [ ] `frontend/public/geo/` 包含 333 个 GeoJSON 文件
- [ ] `loadGeoJson()` 改为直接 fetch 静态文件
- [ ] 热力图组件（HeatMap.vue）正常渲染城市地图
- [ ] 地图加载无需登录认证
- [ ] Git 仓库中包含全部 GeoJSON 文件
