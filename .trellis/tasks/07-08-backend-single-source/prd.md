# 后端多源代码清理与单源硬编码

## Goal

删除所有非 creprice 的数据源代码、导入服务、定时采集、数据质量、地图获取等已砍功能的后端实现，将 source_policy 精简为 creprice-only。

## Dependencies

依赖 07-08-db-restructure 完成（ORM 模型已删除后才能安全清理引用）。

## Requirements

### 删除的文件
| 文件 | 原因 |
|---|---|
| `collector/sources/gov_stats.py` | NBS 指数采集器，功能已砍 |
| `collector/sources/kaggle_lianjia.py` | 链家历史数据，从未在管线中使用 |
| `collector/sources/listing_annual.py` | 58/安居客年度数据解析 |
| `services/nationwide_import.py` | 全国年度数据导入服务 |
| `services/index_import.py` | NBS 指数导入服务 |
| `services/data_quality.py` | 数据质量报告 |
| `services/collect_scheduler.py` | 定时采集调度器 |
| `services/geo.py` | 地图获取服务（地图改为前端静态） |
| `api/v1/admin_data_quality.py` | 数据质量 API |
| `api/v1/geo.py` | 地图 API |

### 精简的文件
- `core/source_policy.py` — 只保留 creprice 一个源的定义，删除 SOURCE_PRIORITY 多源映射
- `stores/source.ts`（前端）— 由 ui-overhaul 子任务处理

### 清理引用
- API 路由注册（router include）中移除已删除模块的路由
- FastAPI lifespan 中移除定时采集调度器启动逻辑
- 所有 import 残留引用需清除
- `data/geo/` 目录删除（地图文件迁移到前端后）

### 保留
- `collector/base.py` + `SourceRegistry` — creprice 仍通过注册模式加载
- `collector/sources/creprice.py` — 不变
- `services/collect_tasks.py` — 采集任务执行器，不变
- `pipeline/` — 采集管线，不变

## Acceptance Criteria

- [ ] 所有列出的文件已删除
- [ ] `source_policy.py` 只含 creprice 定义
- [ ] 无 import 残留引用（`grep` 验证）
- [ ] API 路由注册无已删除模块
- [ ] FastAPI lifespan 无定时采集调度器
- [ ] `data/geo/` 目录已删除
- [ ] 后端应用可正常启动（无 ImportError）
- [ ] 采集功能（手动采集 creprice）仍正常工作
