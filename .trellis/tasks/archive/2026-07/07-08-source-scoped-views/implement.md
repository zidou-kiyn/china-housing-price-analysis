# 执行计划——源隔离展示

## 顺序（后端先行，前端依赖后端 source 参数）

### A. 后端契约与合并删除
1. `app/core/source_policy.py`：加 `REGISTERED_SOURCES`（SOURCE_PRIORITY 键按优先级
   排序的 tuple）、`DEFAULT_SOURCE="creprice"`；删 `priority_case` 及其 `case`/`Case`
   导入（确认无其他引用）。
2. `app/api/deps.py`：加 `source_param` 依赖（Query 缺省 DEFAULT_SOURCE，非登记源 422）。
3. `app/services/price_select.py`：删 `select_merged_snapshots` 及 `priority_case` 导入；
   加 `select_snapshots_for_source(session, source, region_type, region_ids)`。
4. `app/api/v1/prices.py`：`price_trend` 加 `source=Depends(source_param)` 走单源、
   缓存键加 source；`price_distribution` 加 source，`source!=creprice` 返回 []；
   `district_overview` 加 source，max-month 子查询与快照查询都 `WHERE source==source`、
   缓存键加 source。加 `GET /prices/index/trend` + schema `IndexTrendPoint`。
5. `app/api/v1/analytics.py`：`_load_snapshots` 加 source 形参走单源；rank/compare/
   map_heat 加 `source=Depends(source_param)`、缓存键加 source。

**验证 A**：`docker compose exec backend uv run pytest tests/api/test_prices.py
tests/api/test_analytics.py tests/services/test_price_select.py -q`
（先改测试见步骤 6，再跑）。`grep -rn select_merged_snapshots app/ tests/` 无残留。

6. 测试更新：`test_price_select.py` 删 merged 用例、加 for_source 用例；
   `test_prices.py` 改写 merge 用例为单源、加 source=58 / 非法 source / index_trend；
   `test_analytics.py` 加 source 分支。

### B. 前端全局源 + 串参 + 各视图
7. `src/stores/source.ts`：Pinia store + localStorage 持久化 + SOURCE_OPTIONS + isIndex。
8. `src/api/price.ts` / `analytics.ts`：trend/distribution/overview/rank/compare/mapHeat
   加 source 参数；加 `fetchIndexTrend`。类型 `src/types` 按需加 IndexTrendPoint。
9. `src/components/layout/AppHeader.vue`：插全局源 el-select。
10. 五视图（Home/Rank/Compare/Map/Dashboard）：加/扩 watch(source) 重拉；带 source；
    index 源分支（走势调 index，其余"指数源不适用"）；无数据 el-empty。
11. `PredictView.vue` 与各视图预测入口：预测仅 creprice 源可见/可用（R5）。

**验证 B**：`docker compose exec frontend npm run build`。浏览器（Playwright）实测：
泉州 creprice 只显 2025-07 起月度；切 58 年度为年度点带年份；切 NBS 走势为指数曲线、
rank/compare/map 显示不适用；刷新后源保持；非 creprice 下预测入口不可见。

## 审查门 / 回滚点
- 门 1（A 完成）：pytest 相关子集 + grep 无 merged 残留 → 提交后端。
- 门 2（B 完成）：build 通过 + 浏览器实测验收 → 提交前端。
- 回滚：后端删 merged 可 git 还原；前端改造为叠加，回滚不伤存量数据。

## 完成校验（对齐 prd Acceptance）
- [ ] 泉州 creprice 仅 2025-07 起月度、无 58 顶替
- [ ] 58 源走势年度点、rank/compare/map 最新年度值带年份、无月度换算
- [ ] `grep select_merged_snapshots` 全库无残留
- [ ] 切换器刷新保持；非法 source→422
- [ ] NBS 下 rank/compare/map 不适用提示；kaggle 非北京空态
- [ ] 预测入口仅 creprice 可见
- [ ] 全量 pytest + 前端 build 通过
