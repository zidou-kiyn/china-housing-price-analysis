# M1 基础阶段 - 脚手架+采集+入库+基础查询

## Goal

完成系统基础设施搭建与核心数据链路打通：项目脚手架 → 数据库建模 → creprice 采集 → 清洗入库 → 基础 API → 前端搜索与图表。以泉州（qz）为首个打通城市。

## Requirements

- 参见 `docs/08-开发计划与里程碑.md` M1 章节
- 6 个子任务按依赖顺序推进：infra-scaffold → db-schema → collector-creprice → pipeline-clean-load → api-metadata-price → fe-search-chart-trend

## Acceptance Criteria

- [ ] `docker-compose up` 一键启动 PostgreSQL + Redis + Backend + Frontend
- [ ] 触发 creprice 泉州采集 → 原始 JSON 落地 → 清洗入库成功
- [ ] API 可查到泉州及其区县均价、≥12 个月走势数据
- [ ] 前端搜索泉州 → 显示区县柱状图 → 点击区县 → 显示走势折线图
- [ ] crawl_log 正确记录采集 URL、状态、耗时

## Children

- `07-06-infra-scaffold` — 项目脚手架
- `07-06-db-schema` — 数据库模型与迁移
- `07-06-collector-creprice` — creprice 采集适配器
- `07-06-pipeline-clean-load` — 清洗管线与入库
- `07-06-api-metadata-price` — 基础查询 API
- `07-06-fe-search-chart-trend` — 前端搜索与图表
