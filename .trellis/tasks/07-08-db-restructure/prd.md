# 数据库结构精简与种子数据初始化

## Goal

删除无用表、清空历史数据、内置城市种子数据，使全新部署的系统开箱即有完整的城市列表。

## Requirements

### 删除的表（DROP）
- `area` — 片区/街道，creprice 采集管线从未写入
- `community` — 小区，creprice 采集管线从未写入
- `listing` — 房源挂牌，creprice 采集管线从未写入
- `price_index_snapshot` — NBS 指数数据，功能已砍

### 清空的表（TRUNCATE）
- `price_snapshot`、`price_distribution`、`district`、`prediction`
- `admin_job`、`crawl_job`、`crawl_log`
- `app_setting`（清除所有 key，表结构保留）

### 保留的表
- `city` — 种子数据填充
- 用户系统相关表 — 完全不动

### 种子数据
- 从当前 `city` 表导出完整城市列表（name、code、province、adcode）为 JSON
- 存放于 `backend/seed/cities.json`，随代码提交
- 应用启动时检测 `city` 表为空则自动导入

### ORM 模型
- 删除 `Area`、`Community`、`Listing`、`PriceIndexSnapshot` 模型定义文件
- 从 `models/__init__.py` 移除相关导出

### 实现方式
- Alembic migration 实现 DROP 和 TRUNCATE
- migration 兼容全新库（表不存在跳过 DROP）和旧库升级

### `source` 列
- `price_snapshot.source` 列保留不改，默认值硬编码 `"creprice"`

## Acceptance Criteria

- [ ] Alembic migration 成功执行：DROP 4 张表，TRUNCATE 7 张表+清空 app_setting
- [ ] ORM 模型文件已删除，`models/__init__.py` 无残留引用
- [ ] `backend/seed/cities.json` 包含 330+ 城市（含 province 和 adcode）
- [ ] 应用启动时 city 表为空自动导入种子数据
- [ ] 全新 docker compose up 后 city 表已填充
