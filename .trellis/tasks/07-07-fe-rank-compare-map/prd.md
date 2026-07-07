# M2-3 前端排行/对比/地图页

## Goal

基于 M2-2 三个分析端点，交付排行榜、多区域对比、地图热力三个页面，并引入全局导航布局。

## Requirements

### 全局布局

- 新增 `components/layout/AppHeader.vue`：站点标题 + `el-menu` 水平导航（首页 / 排行榜 / 区域对比 / 地图热力），路由高亮。
- `App.vue` 挂载 AppHeader + RouterView；HomeView 原有页内标题降级为城市选择工具栏。

### RankView（/rank）

- 粒度切换（城市榜 / 区县榜），区县榜需选城市（默认泉州）。
- `el-table` 列：排名、区域名、供给价、价值价、环比%、同比%、数据月份；环比/同比红涨绿跌。
- 表头点击切换 sort_by/sort_order（服务端排序，重新请求）。
- 无价格区域展示 `-`，排在最后。

### CompareView（/compare）

- 城市选择 → 区县多选（`el-select multiple`，限 2~5 个）→ 叠加走势折线图。
- 新增 `components/CompareLine.vue`：每区域一条线，legend 可切换，tooltip 同轴对比。
- 选择不足 2 个时提示引导文案，不发请求。

### MapView（/map）

- ECharts `map` 系列 + visualMap 连续色阶（低价绿 → 高价红），数据来自 `/map/heat`。
- GeoJSON 从 `/geo/{cityCode}.json` 异步加载并 `registerMap`；文件缺失时提示"该城市暂无地图数据"。
- 泉州 GeoJSON（`frontend/public/geo/qz.json`，DataV 12 区划）随仓库内置；库中非标准区划（台商投资区/高新区/经开区）地图不着色，忽略即可。
- 点击已着色区县 → 弹出 dialog 展示该区县近 12 个月走势（复用 TrendLine）。

### API 与类型

- `api/analytics.ts`：`fetchRank`、`fetchCompare`、`fetchMapHeat`；`types/index.ts` 补充对应接口类型。

## 约束

- 本任务不做鉴权（对比/地图收权由 M2-4 路由守卫实现）。
- 复用现有组件模式（echarts init/dispose/resize、watch 重渲染）。
- 质量门槛：`npm run type-check`、`npm run build` 通过；浏览器实测三页面渲染与交互。

## Acceptance Criteria

- [ ] /rank 泉州区县榜按均价降序展示，含同比/环比着色
- [ ] /compare 选 2~3 个区县走势叠加、legend 区分
- [ ] /map 泉州 12 区划着色热力图，点击区县弹出走势
- [ ] 导航菜单四页面互通，当前页高亮
- [ ] type-check 与 build 通过
