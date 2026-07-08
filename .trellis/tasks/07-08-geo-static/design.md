# GeoJSON 迁移至前端静态资源 — 技术设计

## 概览

将 333 个 GeoJSON 文件从 `data/geo/` 移动到 `frontend/public/geo/`，修改前端 `loadGeoJson()` 为直接 fetch 静态文件，移除后端地图 API 依赖。

## 文件迁移

```
data/geo/*.json (333 files, ~25MB)
  → frontend/public/geo/*.json
```

Vite 会将 `public/` 目录下的文件原样复制到构建产物根目录，所以生产环境下路径为 `/geo/{city_code}.json`。

## 前端改造

### utils/geo.ts

当前实现：
```typescript
// 调用后端 API
const res = await axios.get(`/geo/${cityCode}`)
```

改为：
```typescript
// 直接 fetch 静态文件
const res = await fetch(`/geo/${cityCode}.json`)
const geoJson = await res.json()
```

- `registeredMaps` 内存缓存逻辑不变
- 移除 axios/api 依赖
- 无需认证 token

### 错误处理

- 静态文件 404（城市地图不存在）：与当前行为一致，catch 并 console.warn
- 不需要认证失败处理（公开资源）

## 清理

### 前端
- `api/admin.ts` 中移除地图相关的 API 调用（如 `fetchGeo`、`crawlMaps` 等）
- `types/index.ts` 中移除地图相关类型（如有）

### 后端
- 已由 backend-single-source 子任务处理（删除 `services/geo.py` 和 `api/v1/geo.py`）

### 数据目录
- 已由 backend-single-source 子任务处理（删除 `data/geo/`）

## Git 影响

- 新增约 25MB 的 JSON 文件到仓库
- 这些文件是静态地理边界数据，变更频率极低
- 不需要 Git LFS（文件尺寸合理）
