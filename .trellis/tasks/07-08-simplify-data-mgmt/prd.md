# 数据管理页面精简与单源化改造

## Goal

将系统从多数据源架构精简为 creprice 单源架构，大幅简化数据管理页面 UI，实现"git clone → docker compose up → 立即可用"的开箱体验。

## Background

当前系统支持 creprice、kaggle_lianjia、listing_annual_58、listing_annual_anjuke、nbs_index 等多个数据源，但实际训练/预测已硬编码为 creprice-only（见 creprice-first 方针）。多源架构带来了大量 UI 复杂度（数据源切换、交叉验证、多源导入）和后端冗余代码，对终端用户无实际价值。

## Scope

本父任务拥有整体需求定义和跨子任务验收标准。实际实现分为 4 个子任务：

1. **07-08-db-restructure** — 数据库结构精简与种子数据初始化
2. **07-08-backend-single-source** — 后端多源代码清理与单源硬编码
3. **07-08-geo-static** — GeoJSON 迁移至前端静态资源
4. **07-08-ui-overhaul** — 数据管理页面 UI 精简与省份-城市树重构

### 执行顺序

1 → 2 → 3 → 4（每个子任务依赖前一个的完成）

## Cross-child Acceptance Criteria

- [ ] docker compose up 后系统可用，无需手动导入数据或配置
- [ ] 数据管理页面只展示 creprice 相关功能，无多源痕迹
- [ ] 省份-城市树形列表正常展示，选择/采集功能完整
- [ ] 城市地图从前端静态资源加载，无后端依赖
- [ ] 所有被删除的后端模块无残留引用（import、路由注册等）
- [ ] Alembic migration 可正确执行（全新库和旧库升级两种场景）
