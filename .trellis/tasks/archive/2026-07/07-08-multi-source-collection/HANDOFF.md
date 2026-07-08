# 多源采集 —— 会话交接（给下一个会话）

> 更新：2026-07-08（第三轮）。child E 完成后又完成 **source-isolation（源独立存储+口径治理）**：修复了 58 覆盖北京 kaggle 数据的污染，走势图按源分线，排行标注口径。

## ✅ 已完成并提交（全量测试 249 passed）

| 子任务 | 状态 | 交付 |
|---|---|---|
| **child A** `07-08-source-framework` | ✅ 完成 | 多源框架：能力声明 `capabilities`/`price_unit`、runner 按能力编排、源解析（请求>KV>默认）、`price_snapshot.source` 列（迁移 004）、`GET/PUT /admin/collect/sources`、前端「数据源」切换卡片 |
| **child C** `07-08-kaggle-import` | ✅ 完成 | `kaggle_lianjia` 源：北京 82 个月历史成交均价落库 + 前端首页真实走势可见 |
| **child E** `07-08-nationwide-annual` | ✅ **完成（本轮）** | 58 全国年度导入：`listing_annual.py` 下载/解析 + `nationwide_import.py`（name→city_id，330 城/3206 快照，35 城跳过）+ `POST /admin/collect/import-annual` + 管理页导入按钮/统计条 + `TrendPoint.source` 字段与前端「年度·挂牌」口径标注（tooltip+图注）。幂等已验证。anjuke 补缺**未做**：latest-wins 会覆盖 58 值，需"仅缺失才写"逻辑，留待需要 |
| **child** `07-08-source-isolation` | ✅ **完成（本轮）** | 源独立存储：迁移 005 唯一键加 source（各源永不互相覆盖）、`source_policy.py` 优先级唯一定义、`price_select.py` 读取合并唯一入口（trend/rank/compare/ML 全接入）、`GET /prices/trend/series` 分源序列、前端走势图按源分线（月度实线/年度虚线）+ 排行/对比「年度·挂牌」标签、北京 kaggle 成交 12 月点已恢复（82 行）与 58 年度行共存 |
| **child B** `07-08-govstats-source` | ⚠️ 适配器完成 | `GovStatsSource` easyquery 客户端+解析器+离线测试+注册可见；**live 抓取阻塞**（见下） |
| **child D** `07-08-agency-scrape` | ⏸️ 暂缓 | 中介站直采：缺住宅 IP + 无可用开源库，已留档 |

## ⏳ 未完成（下一会话可选方向）

### 0. ML 多源训练集构建器【✅ 已完成（07-08-ml-optimization 父任务）】
四个子任务全部落地并归档（archive/2026-07/07-08-ml-{dataset-builder,train-eval,predict-coverage,model-governance}）：
多源训练集构建器（**逐年分段比值曲线**校准，原"单一折价系数"方案被重叠期实证否定——比值 0.79→1.09 漂移）、
naive 基线/RF CV/分层评估（看 `metrics_real_monthly` 不看全量 metrics）、
年度城市预测覆盖（330 城 404→200，data_quality 标注）、版本治理（删除/清理/最佳标注，active→v1.7）。
约定已入 spec：`.trellis/spec/backend/database-guidelines.md` §ML training-data path。
未做的遗留方向：跨城池化独立年度模型、NBS 70 城指数月度插值、ANNUAL_CI_PENALTY 回测校准。

### 1. NBS 70 城指数导入（child B 的务实替代路径）【可选】
- **关键发现**：live easyquery 被 WAF 拦（连国内机房 IP 也 403，见下），但**已抓好的 NBS 70 城指数 CSV 在 GitHub 全球可下**，绕开 IP 问题：
  - `changao1/.../merged_housing_data_eng.csv`（70 城月度指数 2011–2026，GitHub Action 月更）
  - `hugohe3/70cityprice`（含 ADCODE）
- 需要：`price_index_snapshot` 新表 + loader + 指数读 API + 前端指数展示（govstats.md §8 有 schema 建议）。
- 比死磕 live easyquery 实际得多。

## 🚫 阻塞项（需用户提供资源，非代码能解决）

### 代理测试结论（2026-07-08，socks5 8.138.99.54:2260 广州阿里云）
测了用户给的国内 SOCKS5 代理，**是真国内 IP 但是机房 IP，解锁不了目标源**：
| 目标 | 结果 |
|---|---|
| 出口 IP | ✅ 8.138.99.54 广州·阿里云·CN |
| 国家统计局 easyquery | ❌ **仍 403 UrlACL**（WAF 连境内机房 IP 也拦） |
| creprice | ❌ 000 连不通（疑封阿里云段，比直连差） |
| 链家/安居客深层页 | ❌ pg2=302、/fangjia/=302、anjuke=302（反爬照触发） |

**根因是"住宅 IP vs 机房 IP"，不是"境内 vs 境外"。** 要解锁 govstats live / 稳定 creprice / 中介站，需**国内住宅 IP**（住宅代理池），机房代理无效。
→ 但 govstats 数据可用 GitHub 现成 CSV 绕开（见上「2」），是更优路径。

## 建议的下一会话顺序
1. ~~child E（全国年度导入）~~ ✅ 已完成（330 城/3206 快照落库并验证）。
2. 若要官方指数：做 **NBS 70 城指数 CSV 导入**（新表 + 展示），别再等 easyquery。
3. creprice 月度实时：现有源，间歇限流，健康时可用；稳定性待住宅 IP。
4. 中介站：仍暂缓，除非拿到住宅代理池。
5. （小项）anjuke 年度补缺：源独立存储后已无覆盖风险，直接 `import_annual(session, "anjuke")` 即可（各存各的，读取层优先 58）。

## 关键文件/研究
- 研究：`research/DECISION.md`、`nationwide-datasets.md`、`govstats.md`、`kaggle-datasets.md`、`agency-antibot.md`、`integration-design.md`
- 框架代码：`backend/app/collector/base.py`、`sources/{creprice,kaggle_lianjia,gov_stats}.py`、`pipeline/runner.py`、`api/v1/admin_collect.py`、`frontend/src/views/admin/DataManageView.vue`
