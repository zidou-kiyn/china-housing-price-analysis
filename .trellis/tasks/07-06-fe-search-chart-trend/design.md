# 技术设计 - 前端搜索与图表

## 文件结构

```
frontend/src/
├── api/
│   ├── index.ts          # axios 实例（已有）
│   └── price.ts          # 价格相关 API 调用
├── types/index.ts         # 更新类型定义
├── views/
│   └── HomeView.vue       # 主页面（搜索 + 图表）
├── components/
│   ├── CitySelect.vue     # 城市下拉选择器
│   ├── DistrictBar.vue    # 区县均价柱状图
│   ├── TrendLine.vue      # 走势折线图
│   └── DistributionPie.vue # 价格分布饼图
└── composables/
    └── usePrice.ts        # 价格数据组合式函数
```

## 数据流

```
用户选择城市
  → fetchOverview(city_code) → 柱状图数据
  → fetchTrend(city, city_id) → 城市走势
  → fetchDistribution(city, city_id) → 分布饼图

用户点击柱状图中的区县
  → fetchTrend(district, district_id) → 区县走势折线图
```

## 图表配置

- 柱状图：横轴区县名，纵轴均价（元/㎡），使用 ECharts bar
- 折线图：横轴月份，纵轴均价，双线（供给价 + 价值价），使用 ECharts line
- 饼图：各价格区间占比，使用 ECharts pie
