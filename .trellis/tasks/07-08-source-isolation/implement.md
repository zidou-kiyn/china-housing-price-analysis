# Implement — 多源数据源独立存储与口径治理

小步提交，容器内测试。每步验证命令：`docker compose exec -T backend uv run pytest <files> -q`。

## Step 1 — 迁移 + 模型 + loader
- [ ] `alembic/versions/005_price_snapshot_source_isolation.py`：回填 NULL→'creprice'、source NOT NULL、换唯一约束（up/down，down 按优先级去重有损）。
- [ ] `models/price_snapshot.py`：source 非空、UniqueConstraint 加 source。
- [ ] `core/source_policy.py`：SOURCE_PRIORITY / SOURCE_META / priority CASE。
- [ ] `pipeline/loaders.py`：ON CONFLICT 换新约束名，source 必填。
- [ ] 容器内 `alembic upgrade head`；跑 loaders/nationwide_import/collector 相关测试。
- commit: `feat(db): price_snapshot 唯一键加入 source，多源独立存储（迁移 005）`

## Step 2 — 合并选择入口 + 三个读取方接入
- [ ] `services/price_select.py`：`select_merged_snapshots`（DISTINCT ON + 优先级排序）+ 单测（同月双源→取月度源；纯单源不变）。
- [ ] `analytics.py _load_snapshots`、`predictions.py _load_snapshot_rows`、`prices.py /trend` 接入。
- [ ] 新增共存场景测试：seed 同城同月 creprice+listing 两行，rank/trend 取 creprice 值。
- commit: `feat(service): 读取时按源优先级合并（月度>年度挂牌），修复多源同月随机取值`

## Step 3 — trend split 模式 + schema
- [ ] `schemas/price.py`：`TrendSeries{source, granularity, basis, points}`。
- [ ] `prices.py`：`?split=true` 返回 list[TrendSeries]，独立缓存 key `api:trend:split:*`。
- [ ] `tests/api/test_prices.py`：split 返回按源分组、优先级排序、缓存命中。
- commit: `feat(api): /prices/trend split 模式按源返回多序列`

## Step 4 — 数据修复实跑
- [ ] 重跑 kaggle 导入（runner 直调 bj）；重跑 58 导入验幂等。
- [ ] 验证：北京 2011–2017 各 12 月双行共存；行数统计 kaggle 恢复 82、58 仍 3206；泉州无回归。
- commit: `chore(data): 恢复北京 kaggle 成交 12 月点，与 58 年度行共存`

## Step 5 — 前端分线 + 口径标签
- [ ] `types` + `api/price.ts`：TrendSeries、fetchTrendSeries。
- [ ] `TrendLine.vue`：多 series 渲染（月度实线/年度虚线散点，不跨源连线），图例源标签。
- [ ] `usePrice.ts`/`HomeView`：城市与区县走势改用 split。
- [ ] Rank/Compare 视图：年度挂牌条目加「年度·挂牌」tag。
- [ ] vue-tsc + Playwright 实测北京（三源分线）、泉州（断崖消失）、洛阳（纯年度）。
- commit: `feat(frontend): 走势图按源分线渲染 + 排行口径标签`

## Step 6 — 收尾
- [ ] 全量测试；ML 冒烟（train qz + predict）。
- [ ] 更新 spec（database-guidelines 源独立约定）、HANDOFF、记忆。
- commit: `docs(trellis): source-isolation 收尾`
