# 数据管理页面 UI 精简与省份-城市树重构 — 执行计划

## 前置条件

- 07-08-backend-single-source 已完成（后端 API 变更就绪）
- 07-08-geo-static 已完成（地图加载已改为静态）

## 步骤

### 1. 后端 API 适配

编辑 `backend/app/api/v1/admin_collect.py`：
- `GET /admin/collect/cities` 去掉分页参数（page/page_size），全量返回
- 返回 schema 去掉 `has_geo` 字段
- 保留 `province`、`district_count`、`latest_month` 字段

**验证**：`curl GET /admin/collect/cities` 返回 330+ 条，无分页

### 2. 清理前端 API 层

编辑 `frontend/src/api/admin.ts`：
- 移除导入、数据质量、定时采集、地图爬取、数据源切换相关的 API 函数
- 保留城市列表（去掉分页参数）、采集触发、代理配置、任务查询

编辑 `frontend/src/types/index.ts`：
- 移除已删除功能的类型定义

### 3. 精简 source store

编辑 `frontend/src/stores/source.ts`：
- 评估其他消费者；如果仅数据管理页面使用，可删除整个 store
- 如果分析页面也用，简化为只有 creprice

### 4. 重构 DataManageView.vue — 模板

#### 4a. 删除 UI 组件

移除以下 template 块：
- 数据源选择卡片（source-card）
- 定时采集卡片（schedule-card）
- 数据质量卡片（quality-card）
- 过滤栏中的"导入全国年度数据"、"导入NBS 70城指数"按钮
- 批量操作中的"爬取所选地图"、"补齐全部缺图"、"采集全部缺数据城市"按钮
- 城市表格中的地图状态列

#### 4b. 修改代理卡片

- 说明文字改为仅保留"代理仅作用于数据采集（creprice）。"

#### 4c. 合并搜索框

- 将两个输入框（关键词 + 省份）合并为一个
- placeholder: "搜索省份或城市..."

#### 4d. 构建省份-城市树形表格

- 替换现有 `el-table`：
  - `:data="filteredTreeData"`
  - `row-key="id"`
  - `:tree-props="{ children: 'children' }"`
  - selection 列
- 省份行：显示名称 + 城市计数
- 城市行：勾选框、城市名、城市代码、区县数、最新数据月份

#### 4e. 添加操作按钮

- "反选"按钮
- "采集所选 (N)"按钮（唯一采集按钮）

### 5. 重构 DataManageView.vue — 脚本

#### 5a. 删除无用逻辑

- 移除 currentSource 相关 state/watch/API
- 移除 schedule 相关 state/API
- 移除 quality 相关 state/API
- 移除 onImportAnnual/onImportIndex/onCrawlMaps/onFillMaps/onCollectAllMissing
- 移除分页 state（page/pageSize/total）

#### 5b. 新增树形数据逻辑

```typescript
// 从 API 获取全量城市列表
const allCities = ref<CityInfo[]>([])

// 构建树形数据
const treeData = computed(() => {
  const grouped = new Map<string, CityRow[]>()
  for (const city of allCities.value) {
    const p = city.province || '未知'
    if (!grouped.has(p)) grouped.set(p, [])
    grouped.get(p)!.push(cityToRow(city))
  }
  return Array.from(grouped, ([province, cities]) => ({
    id: `province:${province}`,
    name: province,
    cityCount: cities.length,
    children: cities,
  }))
})
```

#### 5c. 搜索过滤逻辑

```typescript
const searchKeyword = ref('')
const filteredTreeData = computed(() => {
  if (!searchKeyword.value) return treeData.value
  const kw = searchKeyword.value.toLowerCase()
  return treeData.value
    .map(province => {
      if (province.name.includes(kw)) return province  // 省份匹配，全部显示
      const filtered = province.children.filter(c => c.name.includes(kw) || c.code.includes(kw))
      return filtered.length ? { ...province, children: filtered } : null
    })
    .filter(Boolean)
})
```

#### 5d. 选择逻辑

- 省份行勾选 → toggleRowSelection 所有 children
- 反选按钮 → 遍历所有城市行 toggle
- 选中计数只统计叶子节点

### 6. 验证

- [ ] 页面加载无报错
- [ ] 省份列表正常展示（31 省份）
- [ ] 展开省份显示城市列表
- [ ] 省份勾选 → 全选该省城市
- [ ] 全选 → 选中所有城市
- [ ] 反选功能正常
- [ ] 搜索省份名和城市名均可过滤
- [ ] 采集所选功能正常触发后端采集
- [ ] 代理配置功能正常
- [ ] 活跃任务/历史任务正常显示
- [ ] 无控制台报错

## 回滚方案

- `git checkout -- frontend/src/views/admin/DataManageView.vue`
- 恢复相关 API/store/types 文件
