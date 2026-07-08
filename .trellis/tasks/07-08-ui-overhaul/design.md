# 数据管理页面 UI 精简与省份-城市树重构 — 技术设计

## 概览

大幅精简 DataManageView.vue（当前 ~1004 行），移除 6 个功能区域的 UI 和逻辑，将城市扁平表格改为 el-table 树形模式的省份-城市两级结构。

## UI 布局（改造后）

```
┌─ 代理配置 ─────────────────────────────────────┐
│ [开关] 代理URL [测试] [保存] [清除]              │
│ 代理仅作用于数据采集（creprice）。                │
└────────────────────────────────────────────────┘

┌─ 操作栏 ───────────────────────────────────────┐
│ 🔍 搜索省份或城市...  [刷新城市列表] [反选]      │
│ [采集所选 (N)]                                  │
└────────────────────────────────────────────────┘

┌─ 省份-城市树形列表 ────────────────────────────┐
│ ☐ ▶ 北京市 (2)                                 │
│ ☐ ▶ 天津市 (1)                                 │
│ ☑ ▼ 河北省 (11)                                │
│     ☑ 石家庄  sjz  8区  2026-06                │
│     ☑ 唐山    ts   7区  2026-05                │
│     ...                                        │
└────────────────────────────────────────────────┘

┌─ 活跃任务 ─────────────────────────────────────┐
│ （现有逻辑不变）                                 │
└────────────────────────────────────────────────┘

┌─ 历史任务 ─────────────────────────────────────┐
│ （现有逻辑不变，去掉 "scheduled" tag）          │
└────────────────────────────────────────────────┘
```

## 省份-城市树形数据结构

### 后端返回

`GET /admin/collect/cities` 改为全量返回（无分页），按省份分组：

```json
{
  "provinces": [
    {
      "province": "北京市",
      "cities": [
        {"name": "北京", "code": "bj", "province": "北京市", "district_count": 16, "latest_month": "2026-06"},
        ...
      ]
    },
    ...
  ]
}
```

或者：后端仍返回扁平城市列表（全量），前端自行按 province 字段分组构建树。**推荐后者**——前端分组更灵活，后端改动最小。

### 前端树形数据

```typescript
interface ProvinceRow {
  id: string           // 'province:北京市'
  name: string         // '北京市'
  cityCount: number
  children: CityRow[]
}

interface CityRow {
  id: string           // 'city:bj'
  name: string
  code: string
  districtCount: number
  latestMonth: string | null
}
```

`el-table` 配置：
- `:data="treeData"`
- `row-key="id"`
- `:tree-props="{ children: 'children' }"`
- `@selection-change="onSelectionChange"`
- `:default-expand-all="false"`

### 选择逻辑

- **el-table 的 selection 列**：内置支持 `@selection-change`
- **省份行勾选**：手动实现——监听 `@select` 事件，判断是否为省份行，如果是则调用 `toggleRowSelection` 对其所有 children
- **全选**：表头 checkbox，el-table 内置支持（`@select-all`）
- **反选**：自定义按钮，遍历所有城市行，toggle 每个的选中状态
- **选中计数**：只统计叶子节点（城市），不统计省份行

### 搜索过滤

- 前端纯客户端过滤（330 条数据量极小）
- 搜索框 `v-model="searchKeyword"`，`watch` 触发过滤
- 过滤逻辑：
  - 匹配省份名 → 显示该省份行（折叠状态，显示全部城市）
  - 匹配城市名 → 显示所属省份行（展开）+ 匹配的城市
  - 无匹配 → 空状态
  - 清空搜索 → 恢复完整列表，全部折叠

## 移除的 script 逻辑

以下 script 代码段需删除：
- `currentSource` 相关（数据源选择 state + watch + API）
- `scheduleXxx` 相关（定时采集 state + API）
- `qualityXxx` 相关（数据质量 state + API）
- `onImportAnnual()`、`onImportIndex()` 函数
- `onCrawlMaps()`、`onFillMaps()` 函数
- `onCollectAllMissing()` 函数
- 分页相关 state（`page`、`pageSize`、`total`）

## 前端 source store

`stores/source.ts` 移除多源选项，仅保留 creprice。如果 store 仅用于数据管理页面的源选择（已删除），可以整体评估是否还有其他消费者——如果分析页面也用它来决定查询源，则保留但简化。

## API 函数清理

`api/admin.ts` 中需移除的函数：
- 地图爬取相关
- 导入数据相关
- 数据质量相关
- 定时采集配置相关
- 数据源切换相关

## 类型清理

`types/index.ts` 中需移除的类型：
- 数据质量相关类型
- 定时采集相关类型
- 数据源列表相关类型（如有）
