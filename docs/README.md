# 城市房价分析系统 · 开发文档集

> 本目录是**面向开发者的完整开发规划与设计文档**，目标是让开发者据此稳定落地。
> 文档内的**术语表、数据表结构、API 路径为全项目单一事实源**，实现时不得各自发明。

## 一句话产品定义

看懂一座城的房价，并预测它的走势 —— **多源采集 + 可视化分析 + 机器学习预测**。

## 阅读顺序

| 序号 | 文档 | 内容 | 主要读者 |
|------|------|------|---------|
| 00 | [README](./README.md) | 文档导航（本文） | 全体 |
| 01 | [需求规格说明](./01-需求规格说明.md) | 功能/非功能需求、用例、验收 | 全体 / PM |
| 02 | [系统架构设计](./02-系统架构设计.md) | 四层架构、组件、用例图、术语表 | 架构 / 全体 |
| 03 | [数据采集设计](./03-数据采集设计.md) | 数据源画像、Source 适配器、反爬、流水线 | 采集开发 |
| 04 | [数据模型与数据库设计](./04-数据模型与数据库设计.md) | ER 图、建表 DDL、索引、迁移 | 后端 / 数据 |
| 05 | [后端API设计](./05-后端API设计.md) | REST 契约、鉴权、错误码 | 后端 / 前端 |
| 06 | [机器学习预测设计](./06-机器学习预测设计.md) | 特征、模型、评估、推理、版本化 | 算法 |
| 07 | [前端设计](./07-前端设计.md) | 页面、路由、组件、图表、地图 | 前端 |
| 08 | [开发计划与里程碑](./08-开发计划与里程碑.md) | 三阶段、任务分解、排期、验收 | PM / 全体 |
| 09 | [工程规范与部署](./09-工程规范与部署.md) | 目录结构、配置、CI、Docker、测试 | 全体 |

## 技术栈总览

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 · Vite · TypeScript · Pinia · Vue Router · Element Plus · ECharts（含 geo 离线 GeoJSON）· axios |
| 后端 | Python 3.11 · FastAPI · Pydantic v2 · Uvicorn · SQLAlchemy 2.0(async) · Alembic · python-jose(JWT) · passlib(bcrypt) |
| 采集 | requests · lxml · BeautifulSoup · httpx · APScheduler（**仅 requests，不做浏览器自动化采集**；Playwright 仅前期调研用，非项目依赖） |
| 数据/ML | PostgreSQL 16 · Redis 7 · Pandas · NumPy · scikit-learn · XGBoost · joblib |
| 工程 | Docker · docker-compose · pytest · ruff · mypy · pre-commit · GitHub Actions |

## 关键已敲定决策（详见各文档）

1. **数据源混合策略**：主力真实源 `creprice.cn`（反爬弱、含历史时序）；链家/安居客仅演示级；Kaggle 等公开数据集做 ML 底座。见 [03](./03-数据采集设计.md)。
2. **后端 FastAPI**、**前端 Vue3 + ECharts**、**数据库 PostgreSQL**、**缓存 Redis**、**调度 APScheduler**。
3. **ML 目标务实**：RandomForest 达标为主、XGBoost 为提升项，重在跑通全链路。
4. **首个打通城市：泉州（qz）**（creprice 覆盖好、实测过），后续横向扩展。

## 文档维护约定

- 改动数据表结构 → 先改 [04](./04-数据模型与数据库设计.md)，再改代码与其他文档。
- 改动 API → 先改 [05](./05-后端API设计.md)。
- 新术语 → 先进 [02 术语表](./02-系统架构设计.md#附录a-术语表)。
- 所有架构图用 Mermaid 内嵌，GitHub / VSCode（Markdown Preview Mermaid 插件）可渲染。
