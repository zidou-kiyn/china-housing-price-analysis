# M3-2 可视化大屏多图联动

## Goal

新增 DashboardView 大屏页（/dashboard，requiresAuth）：地图热力、区县排行柱状、走势折线、价格分布饼图四图联动——点选区域后各图表同步切换（docs/08 M3-2）。

## Requirements

- 默认城市泉州（qz），默认视角为城市级（走势/分布展示全市数据）。
- 联动：点击地图区县 或 排行柱状图某柱 → 走势 + 分布切换到该区县；地图与柱状图同步高亮选中项；提供「返回全市」恢复城市级视角。
- 顶部工具栏：CitySelect 切换城市（geojson 缺失时地图面板显示提示，其余面板正常）。
- 导航栏新增「大屏」入口。
- 代码复用（不复制粘贴 MapView 逻辑）：
  - geojson 加载/注册抽到 `utils/geo.ts`；
  - 地图渲染抽成 `components/HeatMap.vue`（MapView 重构为复用该组件，行为不变）；
  - `DistrictBar` 增加可选 selectedName 高亮 prop（HomeView 现有用法不受影响）。

## 约束

- 沿用现有浅色主题与 Element Plus 风格，不引入新依赖。
- 数据接口全部复用现有 API（/map/heat、/prices/overview、/prices/trend、/prices/distribution）。

## Acceptance Criteria

- [x] /dashboard 四面板齐全，默认显示泉州全市走势+分布
- [x] 点击地图区县 → 走势/分布切到该区县，柱状图对应柱高亮；点击柱状图亦然，地图同步选中
- [x] 「返回全市」恢复城市级走势/分布并清除高亮
- [x] 游客访问 /dashboard 跳登录；导航栏有「大屏」入口
- [x] MapView 重构后回归正常（选城市、点击区县弹走势）
- [x] npm run type-check && npm run build 通过 + 浏览器实测联动
