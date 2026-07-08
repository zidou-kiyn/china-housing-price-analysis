# 城市等级 seed 数据与特征集成

## Goal

为 city 表添加 tier 字段，使用第一财经 2025 城市等级分类作为 seed 数据，并将 city_tier 纳入 ML 特征集。

## Background

当前模型使用 `region_id` 作为高基数类别特征（368 级），每个 ID 仅 13 条数据，模型难以从中学到有意义的规律。city_tier（6 级）能将相似城市分组，提升模型泛化能力。

## Requirements

### R1: city 表加 tier 字段
- 新增 `tier` 列（smallint，nullable），取值 1-6
- 含义：1=一线, 2=新一线, 3=二线, 4=三线, 5=四线, 6=五线
- 通过 Alembic migration 添加

### R2: seed 数据
- 使用第一财经·新一线城市研究所 2025 年发布的城市等级分类
- 建 seed JSON/CSV 文件，按 city name 或 adcode 匹配
- 系统初始化时自动写入（seed 脚本或 migration data）
- 368 个城市中未能匹配到分类的，tier 设为 NULL 或默认最低档

### R3: ML 特征集成
- `features.py` 的 `build_training_frame` 中加入 `city_tier` 特征
- 通过 region_id → city 表 join 获取 tier 值
- `feature_columns()` 返回值包含 `city_tier`

### R4: API 暴露
- 城市列表 API 返回 tier 字段
- 城市覆盖状态 API 返回 tier 字段

## Acceptance Criteria

- [ ] city 表含 tier 字段，migration 可正向/回滚
- [ ] seed 数据覆盖率 ≥ 90%（至少 330/368 城市有 tier 值）
- [ ] `feature_columns()` 包含 `city_tier`
- [ ] 训练流程能正常使用 city_tier 特征（不报错）
- [ ] 城市列表 API 返回 tier 字段
- [ ] 现有测试通过
