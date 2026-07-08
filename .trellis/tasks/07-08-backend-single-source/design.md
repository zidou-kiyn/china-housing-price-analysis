# 后端多源代码清理与单源硬编码 — 技术设计

## 概览

删除所有非 creprice 数据源代码、已砍功能的后端服务和 API 模块，精简 source_policy 为单源定义，移除定时采集调度器和数据质量模块。

## 删除清单

### 采集器（collector/sources/）
| 文件 | 原因 |
|---|---|
| `gov_stats.py` | NBS 指数采集器，功能已砍 |
| `kaggle_lianjia.py` | 链家历史数据，从未在管线中使用 |
| `listing_annual.py` | 58/安居客年度数据解析 |

### 服务（services/）
| 文件 | 原因 |
|---|---|
| `nationwide_import.py` | 全国年度数据导入 |
| `index_import.py` | NBS 指数导入 |
| `data_quality.py` | 多源交叉验证报告 |
| `collect_scheduler.py` | 定时采集调度器 |
| `geo.py` | 地图运行时获取 |

### API 路由（api/v1/）
| 文件 | 原因 |
|---|---|
| `admin_data_quality.py` | 数据质量 API |
| `geo.py` | 地图获取/查询 API |

### 数据目录
| 路径 | 原因 |
|---|---|
| `data/geo/` | GeoJSON 文件（迁移到前端后删除） |

## 精简清单

### source_policy.py

原内容：4 源优先级、SOURCE_PRIORITY、REGISTERED_SOURCES、TRAINING_SOURCES、SOURCE_META

精简为：
```python
DEFAULT_SOURCE = "creprice"
REGISTERED_SOURCES = ("creprice",)
TRAINING_SOURCES = ("creprice",)
SOURCE_META = {
    "creprice": {"granularity": "monthly", "basis": "listing"},
}
```

保留 `DEFAULT_SOURCE`、`REGISTERED_SOURCES`、`TRAINING_SOURCES`、`SOURCE_META` 这些名称，因为可能有其他模块引用。

### main.py lifespan

- 移除 `collect_scheduler` 的 import、start、stop
- 移除 `_scheduler_enabled()` 函数
- 保留 `cleanup_stale_jobs()` 和 `seed_cities_if_empty()`（db-restructure 子任务已添加）

### API 路由注册

需要从 `api/v1/__init__.py` 或 `main.py` 的 router include 中移除：
- `admin_data_quality` 路由
- `geo` 路由

需要从 admin 路由中移除：
- 定时采集相关的 settings 端点（如果有独立路由）
- 导入相关的端点（import_annual、import_index）

### admin_collect.py 清理

- 移除地图状态查询（`has_geo` 字段计算）
- 移除分页参数（改为全量返回，配合 ui-overhaul）
- 保留城市列表、采集触发、任务查询端点

### admin_settings.py 清理

- 移除定时采集配置端点（GET/PUT collect-schedule）
- 保留代理配置端点（GET/PUT proxy、POST proxy/test）

## 引用扫描策略

删除文件后，用以下命令扫描残留引用：
```bash
grep -rn "gov_stats\|kaggle_lianjia\|listing_annual\|nationwide_import\|index_import\|data_quality\|collect_scheduler\|admin_data_quality" backend/app/
grep -rn "from app.services.geo\|from app.api.v1.geo" backend/app/
grep -rn "price_index_snapshot\|PriceIndexSnapshot" backend/app/
```

## 风险

- `data_quality.py` 被 admin_data_quality.py 引用——两个一起删即可
- `collect_scheduler.py` 被 main.py 引用——需同步清理 lifespan
- `geo.py`（services 和 api 两个）被 admin_collect.py 引用（has_geo 查询）——需清理
- nationwide_import 和 index_import 被 admin_collect.py 的导入端点引用——端点一起删
