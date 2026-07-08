# 多源采集 —— 会话交接（给下一个会话）

> 更新：2026-07-08。本会话完成了框架 + 两个源，验证了全国数据集，测了国内代理。下面是**已完成 / 未完成 / 下一步**。

## ✅ 已完成并提交（10+ commits，全量测试 223 passed）

| 子任务 | 状态 | 交付 |
|---|---|---|
| **child A** `07-08-source-framework` | ✅ 完成 | 多源框架：能力声明 `capabilities`/`price_unit`、runner 按能力编排、源解析（请求>KV>默认）、`price_snapshot.source` 列（迁移 004）、`GET/PUT /admin/collect/sources`、前端「数据源」切换卡片 |
| **child C** `07-08-kaggle-import` | ✅ 完成 | `kaggle_lianjia` 源：北京 82 个月历史成交均价落库 + 前端首页真实走势可见 |
| **child B** `07-08-govstats-source` | ⚠️ 适配器完成 | `GovStatsSource` easyquery 客户端+解析器+离线测试+注册可见；**live 抓取阻塞**（见下） |
| **child D** `07-08-agency-scrape` | ⏸️ 暂缓 | 中介站直采：缺住宅 IP + 无可用开源库，已留档 |

## ⏳ 未完成（下一会话的主任务）

### 1. ★ child E `07-08-nationwide-annual` —— 全国 ~330 城年度房价导入【就绪，直接实现】
- **已验证**：58.com CSV = 365 城、2010–2024 年度 ¥/㎡、MIT、免登录直下；**330/365 城名精确匹配** DB 的 368 城目录。一次导入把有价格数据的城市从 ~5 铺到 ~335。
- **规划齐全**：prd/design/implement 已写好（`.trellis/tasks/07-08-nationwide-annual/`）。按 implement.md 的 5 步做即可。
- **口径注意**：年度 + 挂牌价（非月度成交），用 `source='listing_annual_58'` 区隔、前端标注。
- **下载地址**：`https://raw.githubusercontent.com/changao1/70-China-cities-housing-index-data-by-national-bureau-of-statistics/main/supplementary/58tongcheng_city_avg_price_annual_2010-2024.csv`

### 2. NBS 70 城指数导入（child B 的务实替代路径）【可选】
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
1. 做 **child E**（全国年度导入）—— 最高性价比，把全国城市数据一次铺满。
2. 若要官方指数：做 **NBS 70 城指数 CSV 导入**（新表 + 展示），别再等 easyquery。
3. creprice 月度实时：现有源，间歇限流，健康时可用；稳定性待住宅 IP。
4. 中介站：仍暂缓，除非拿到住宅代理池。

## 关键文件/研究
- 研究：`research/DECISION.md`、`nationwide-datasets.md`、`govstats.md`、`kaggle-datasets.md`、`agency-antibot.md`、`integration-design.md`
- 框架代码：`backend/app/collector/base.py`、`sources/{creprice,kaggle_lianjia,gov_stats}.py`、`pipeline/runner.py`、`api/v1/admin_collect.py`、`frontend/src/views/admin/DataManageView.vue`
