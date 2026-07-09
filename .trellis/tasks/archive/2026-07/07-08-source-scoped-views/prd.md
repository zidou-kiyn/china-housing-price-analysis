# 源隔离展示——全局数据源切换器

## Goal

全站数据展示按源硬隔离：用户通过全局切换器选定一个数据源，所有视图只渲染
该源的原样数据（年度就按年度展示，不做月度换算），彻底移除跨源优先级合并。

## Requirements

- R1 后端 API 源参数：价格/分析类端点统一加 `source` 查询参数——
  `GET /prices/trend`、`/prices/distribution`、`/prices/overview`、
  `/analytics/rank`、`/analytics/compare`、`/analytics/map/heat`。
  取值为 source_policy 已登记源（creprice / listing_annual_58 / kaggle_lianjia），
  缺省 = creprice；非法值 422。NBS 指数走既有 `price_index_snapshot` 路径,
  不混入 ¥/㎡ 端点。
- R2 删除合并路径：`price_select.select_merged_snapshots` 及其两个消费方
  （prices.py:47、analytics.py:73）全部改走 `select_source_snapshots` 单源查询；
  合并函数删除（git 历史可回）。`/prices/trend/series` 多源分线接口保留——
  它是"对比展示"的显式入口，不属于混合。
- R3 全局源切换器（前端）：顶栏单选组件（Pinia 全局状态 + localStorage 持久化，
  默认 creprice），选项带源说明标签（月度实采 / 年度挂牌 / 历史成交 / 官方指数）。
  切换后 HomeView / RankView / CompareView / MapView / DashboardView 全部按所选
  源重新拉数。
- R4 单源渲染口径：
  a) creprice：现状月度口径不变；
  b) 58 年度：走势按年度点连线（沿用「年度·挂牌」虚线样式），排行/对比/地图
     用各区域最新年度值并明确标注年份，不做任何月度插值；
  c) kaggle：仅北京有数据，其余城市显式"该源无数据"空态；
  d) NBS 指数：仅走势视图有意义（指数曲线，单位=指数非价格），排行/对比/地图
     在该源下禁用或显示"指数源不适用"提示。
- R5 预测入口限定：预测页/预测入口仅在当前源为 creprice 时可见可用；
  其他源下隐藏或禁用并说明"预测仅基于 creprice 实采数据"。
- R6 无数据空态：任一源下无该源数据的城市/区域，一律显式空态提示，
  禁止静默回退到其他源（这正是本任务要消灭的行为）。

## Acceptance Criteria

- [ ] 泉州在 creprice 源下只显示 2025-07 起的月度数据，更早月份不再出现
      58 年度数据顶替
- [ ] 切到 58 年度源：走势为年度点、排行/对比/地图为最新年度值且带年份标注，
      无任何月度换算痕迹
- [ ] `select_merged_snapshots` 在代码库中不存在；grep 无残留引用
- [ ] 切换器状态刷新页面后保持；非法 source 参数返回 422
- [ ] NBS 指数源下排行/对比/地图有明确不适用提示；kaggle 源下非北京城市空态
- [ ] 预测入口仅 creprice 源可见
- [ ] 全量 pytest + 前端 build 通过；相关 API 测试覆盖 source 参数分支

## Notes

- source_policy 的源优先级在合并删除后仅剩"切换器选项排序"用途，保留定义。
- 走势图已有按源分线基础（trend/series），R4a/b 大部分是复用而非新写。
- 与 07-08-training-whitelist-cleanup 互相独立，可并行。
