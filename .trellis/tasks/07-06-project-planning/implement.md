# 执行计划 - 城市房价分析系统开发规划

> 本任务的交付物是**文档集**（`docs/`）。本执行计划描述"如何产出并校验这套规划文档"，
> 同时在最后给出"后续系统实现阶段"的任务拆分建议（供之后转成 Trellis 子任务）。

## A. 本规划任务的执行清单（产出文档）

- [x] A1. 解析 `.source/` 需求（docx + pptx），提炼三层功能与四层架构。
- [x] A2. Playwright 实测数据源反爬（链家/安居客/creprice），落地 `research/crawler-source-survey.md`。
- [x] A3. 敲定关键方向（数据源混合策略 / FastAPI / Vue3+ECharts）。
- [x] A4. 编写 Trellis 三件套：`prd.md` / `design.md` / `implement.md`。
- [x] A5. 编写 `docs/` 完整文档集（见下）。
- [x] A6. 一致性校验：术语、表名、字段、API 路径跨文档对齐。
- [ ] A7. 架构图渲染校验：Mermaid 语法在 GitHub/VSCode 预览正常（需用户人工确认）。

### docs/ 文档清单
- [x] `docs/README.md` — 文档导航 + 阅读顺序
- [x] `docs/01-需求规格说明.md`
- [x] `docs/02-系统架构设计.md`（四层架构图/用例图/组件图/术语表）
- [x] `docs/03-数据采集设计.md`（站点画像/Source 适配器/反爬/字段映射/流水线图）
- [x] `docs/04-数据模型与数据库设计.md`（ER 图/建表 DDL/索引/迁移策略）
- [x] `docs/05-后端API设计.md`（端点契约/请求响应示例/鉴权/错误码）
- [x] `docs/06-机器学习预测设计.md`（特征工程/模型/评估/版本化/推理流程）
- [x] `docs/07-前端设计.md`（页面/路由/组件/图表规格/地图/状态管理）
- [x] `docs/08-开发计划与里程碑.md`（三阶段/任务分解/排期/验收口径）
- [x] `docs/09-工程规范与部署.md`（目录结构/环境/配置/CI/Docker/测试）

## B. 校验命令

```bash
# 文档存在性
ls docs/
# Mermaid 语法可用在线校验或 VSCode Markdown Preview Mermaid Support 插件
# 一致性检查（术语/表名抽样）
grep -rn "price_snapshot\|/api/v1" docs/
```

## C. 后续系统实现阶段的任务拆分建议（转 Trellis 子任务）

> 待本规划文档评审通过后，可用 `task.py create ... --parent <本任务>` 拆分为以下子任务。
> 每个子任务可独立实现、独立验证。

### 阶段 M1（基础，第 1 月）
1. **infra-scaffold**：项目脚手架（backend/frontend/docker-compose/CI），PostgreSQL+Redis 起环境，健康检查端点。
2. **db-schema**：SQLAlchemy 模型 + Alembic 初始迁移（city/district/community/listing/price_snapshot/...）。
3. **collector-creprice**：creprice.cn 静态适配器 + 调度 + 原始落地 + crawl_log。
4. **pipeline-clean-load**：清洗/去重/标准化 → 入库；单元测试覆盖字段映射。
5. **api-metadata-price**：`/cities`、`/districts`、`/regions/{id}/price`、`/regions/{id}/trend`。
6. **fe-search-chart-trend**：搜索页 + 柱状图 + 走势折线（ECharts）。

### 阶段 M2（增强，第 2–3 月）
7. **collector-agency-demo**：链家/安居客 Playwright 演示级适配器 + 反爬处理（小样本）。
8. **api-rank-compare-map**：`/rank`、`/compare`、`/map/heat`。
9. **fe-compare-map**：跨城对比 + ECharts geo 地图热力（离线 GeoJSON）。
10. **auth-rbac**：JWT 登录注册 + 三角色权限；前端路由守卫。
11. **ml-pipeline-rf**：特征工程 + RandomForest 训练/评估/推理 + `prediction` 表 + `/predict/{id}`。

### 阶段 M3（完善，3 月后）
12. **ml-xgboost-tuning**：XGBoost + 交叉验证调优 + 模型对比与切换。
13. **fe-dashboard**：可视化大屏（多图联动）。
14. **testing-hardening**：端到端测试、压测、错误处理、日志与监控。
15. **deploy**：Docker 镜像 + docker-compose 生产配置 + 部署文档。

## D. 回滚点

- 文档阶段：文档在 git 版本控制内，评审不通过可回退到上一版。
- 实现阶段：每个子任务独立分支/独立可回滚（迁移 downgrade、镜像回退、模型版本切换）。

## E. Definition of Done（本规划任务）

- docs/ 全部文档产出且内部一致；架构图可渲染；design/implement/prd 齐备。
- 用户评审通过关键方向；后续实现子任务清单明确、可直接开工。
