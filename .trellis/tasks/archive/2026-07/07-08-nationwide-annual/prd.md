# 全国城市年度房价导入（child E）

> 父任务：`07-08-multi-source-collection`。依赖 child A（多源框架）。**本会话已完成可行性验证，待实现。**
> 研究依据：`../07-08-multi-source-collection/research/nationwide-datasets.md`。

## 背景（已实测验证）

之前只有京沪深级别的现成数据；本轮找到覆盖**全国 365 城**的公开数据集：GitHub 仓库 `changao1/70-China-cities-...` 的 `supplementary/58tongcheng_city_avg_price_annual_2010-2024.csv`：

- **365 个城市，32 个省，2010–2024 年度 ¥/㎡**，MIT 许可，106KB，免登录 `curl` 直下。
- 字段：`province,city,year,price_yuan_per_sqm,yoy_pct`。
- **实测：365 城中 330 城的城市名与本项目 368 城目录精确匹配** → 一次导入即可把"有价格数据的城市"从当前 ~5 个铺到 ~335 个。
- 数值合理（北京 2024=58950、洛阳 6792、克拉玛依 5278、三亚 29787 ¥/㎡）。
- 配套 `anjuke_city_avg_price_annual_2015-2024.csv`（349 城）可做交叉校验/补缺。

## Goal

导入 58.com 365 城年度挂牌均价，按城市名匹配落库到 ~330 城的城市级快照（`source='listing_annual_58'`），把全国城市地图从"3 城有数据"变为"全国铺满"。年度挂牌口径用 `source` 列与前端标注区隔，不与 creprice 月度线混为一条。

## 约束与口径

- **年度 + 挂牌均价（非月度成交）**：`year_month` 落 `YYYY-12`；`supply_price=price_yuan_per_sqm`；`sample_count=NULL`。挂牌价略高于成交，须标注。
- **名称键 vs 代码键**：CSV 按城市**名**，DB 按 creprice **code**。导入时做 name→city_id 匹配；35 个未匹配城市（县级市/自治州/香港等，如义乌/昆山/巢湖/兴安盟）跳过并记录，不新建脏城市行。
- 不走 `PipelineRunner` 的按-city_code 爬取管线（阻抗不匹配），用**独立批量导入**路径，复用 `upsert_price_snapshots`。

## Acceptance Criteria

- [x] 下载+解析 58 CSV（缓存到 gitignore 的 data/listing/），离线解析单测（7 个）。
- [x] 批量导入：name→city_id 匹配，**330 城**落库 **3206 条**年度快照，`source='listing_annual_58'`，返回覆盖统计；35 城未匹配跳过（义乌/昆山/兴安盟/香港等，与预期一致）。
- [x] 管理端可触发导入：`POST /admin/collect/import-annual`（同步，require_admin）；skipped_cities 在响应与日志中可见。
- [x] 前端首页抽查洛阳/克拉玛依/三亚/桂林（Playwright 实测），走势图渲染年度点；价格与研究预测一致（洛阳 6792、克拉玛依 5278、三亚 29787）。
- [x] creprice/kaggle 无回归（泉州月度点完好，全量 249 passed）；导入幂等（UI 重跑统计不变）。
- [ ] （可选，未做）anjuke 349 城补缺：当前 upsert 为 latest-wins，直接导会覆盖 58 同城同年值而非"补缺"，需先加"仅缺失才写"逻辑，留待需要时做。
