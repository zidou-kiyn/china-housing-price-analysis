# Kaggle 公开数据集导入源（child C）

> 父任务：`07-08-multi-source-collection`。依赖 child A（多源框架）。本环境唯一能产出真实数据的可靠新源。

## Goal

把 Kaggle 公开数据集 `ruiqurm/lianjia`（北京 2011–2017 二手房成交明细，31.8 万行）实现为一个 `BaseSource`，按月聚合为城市级成交均价（¥/㎡），复用现有 pipeline 落库，作为**历史回填 + 交叉校验**的可靠新源。

## Requirements

1. 新增 `KaggleLianjiaSource`（source_name=`kaggle_lianjia`），注册进框架，前端切换 UI 可见。
2. 能力 `{CITIES, PRICE_TIMELINE}`，`price_unit=cny_per_sqm`；无区县、无价格分布（MVP 城市级）。
3. Kaggle 公开数据集**免登录直连下载**（302→签名 GCS），本地缓存（`data/kaggle/`，已 gitignore），重复采集不重复下载。默认直连（不走美国代理）。
4. 按 `tradeTime` 的 YYYY-MM 聚合：`supply_price=成交均价`、`sample_count=成交笔数`；过滤单价异常与每月过少样本（<30 笔）。
5. 城市 code 对齐库内既有 `bj`，使快照落到同一北京城市行。
6. 语义差异（Kaggle=成交价，creprice=挂牌价）由 `price_snapshot.source` 溯源；许可（CC BY-NC-SA 非商业）在文档/源码注明，仅用于本系统分析。
7. `/cities` 列表纳入"有城市级快照"的城市（否则北京无区县不可见），保持既有"有区县"城市不变。

## 非目标（MVP）

- 区县级聚合（1–13 编码映射，跨源区县码对齐）——后续增强。
- 上海/深圳数据集（单时点快照，字段各异）——后续可加，源已留扩展位。
- 定时/自动同步（静态历史数据集，手动触发即可）。

## Acceptance Criteria

- [x] `kaggle_lianjia` 注册成功，`GET /admin/collect/sources` 可见其能力与 price_unit。
- [x] 通过 pipeline 采集 `bj` 落库北京城市级历史快照（真实值，source=`kaggle_lianjia`）。
- [x] 前端首页可选北京并渲染整体走势（2010–2017，¥/㎡ 真实轨迹）。
- [x] 离线解析单测（聚合/过滤/非北京拒绝）通过；`/cities` 纳入逻辑有回归测试。
- [x] creprice 及既有城市展示无回归。
