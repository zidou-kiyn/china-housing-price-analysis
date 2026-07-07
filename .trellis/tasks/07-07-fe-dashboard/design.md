# M3-2 技术设计

## 改动面

| 文件 | 改动 |
|------|------|
| `src/utils/geo.ts`（新） | `loadGeoJson(cityCode): Promise<boolean>`：fetch `/geo/{code}.json` → `echarts.registerMap`，模块级 Set 去重（自 MapView 抽出） |
| `src/components/HeatMap.vue`（新） | 纯展示地图：props `{ mapName, items: MapHeatItem[], selectedName?, height? }`，emits `select(item)`；`selectedMode:'single'`，watch selectedName → dispatchAction select/unselect |
| `src/views/MapView.vue` | 重构为 loadGeoJson + HeatMap，点击弹窗行为不变 |
| `src/components/DistrictBar.vue` | 可选 prop `selectedName`：选中柱换主题深色，其余照旧 |
| `src/views/DashboardView.vue`（新） | 四面板 grid + 联动 state |
| `src/router/index.ts`、`AppHeader.vue` | /dashboard 路由（requiresAuth）+ 「大屏」导航 |

## 联动状态

```ts
selected: { type: 'city' | 'district'; id: number; name: string }
```

- 初始 = 当前城市；`onCityChange` 重置。
- HeatMap.select / DistrictBar.select → 设为该区县 → watch selected 拉 fetchTrend/fetchDistribution。
- 高亮：selectedName 传给 HeatMap（dispatchAction）与 DistrictBar（柱色）；返回全市置 null。
- 面板数据源：HeatMap ← fetchMapHeat；DistrictBar ← fetchOverview；Trend/Pie ← fetchTrend/fetchDistribution（city 用 city.id，district 用 district id）。

## 布局

el-row/el-col 两行两列（地图与柱状上排，走势与分布下排），面板用 el-card；工具栏含 CitySelect + 当前区域 el-tag + 返回全市按钮。
