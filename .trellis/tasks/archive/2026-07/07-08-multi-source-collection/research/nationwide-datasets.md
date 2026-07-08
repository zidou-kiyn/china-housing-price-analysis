# 全国多城市房价数据集调研（覆盖广度专项）

> 任务：为「多源采集」找**覆盖全国、尽量多城市**的公开房价数据集，用于历史回填。
> 前序结论（`kaggle-datasets.md`）：现成静态数据集只覆盖京沪深三城。本轮专攻**广度**。
> 调研日期：2026-07-08。**所有数字均为实测**：下载后 `unzip -l` + 表头抽查 + `cut|sort -u|wc -l` 统计 distinct 城市，非凭标题臆测。
> 临时数据：`scratchpad/kaggle_nationwide/`（58_city_avg.csv, anjuke_city_avg.csv, merged_70city_index.csv, china-main-city.zip）。

---

## 0. 结论速览（决策级）

- **最广覆盖 = 366 个城市**（不是几十，是几乎全国）。来自 GitHub 仓库 **`changao1/70-China-cities-...`** 的 `supplementary/` 目录，两份免登录 CSV：
  - **58.com：365 城**，2010–2024 **年度** ¥/㎡，MIT 许可，字段 `province,city,year,price_yuan_per_sqm,yoy_pct`。
  - **anjuke：349 城**，2015–2024 **年度** ¥/㎡，同结构、同许可。
  - 两份并集 **366 个不同城市，覆盖 32 个省级行政区**（全部大陆省份 + 香港）。这是本项目 368 城目录的近乎全量匹配。
- **是否存在"全国 100+ 城市 *月度* ¥/㎡"的免费开放数据集？→ 没有。** 免费开放且能直接下载的数据里：
  - **要广度（300+ 城、绝对 ¥/㎡）→ 只有年度**（上面这份 366 城年度）。
  - **要月度 + 广度（70 城）→ 只有指数**（国家统计局 70 城指数，环比/同比≈100，**不是 ¥/㎡**）。
  - **要月度 + 绝对 ¥/㎡ → 只有单城/少城快照**（京沪深；Kaggle 10 城是单月截面）。
  三者不可兼得。真正的"全国 340~626 城 **月度** ¥/㎡ 面板"**存在但不免费**（经管之家 pinggu.org 付费帖，见 §5），或需自采（anjuke/58 城市页、creprice）。
- **一句话给决策**：想一次性把"城市维度"铺满全国，就导 **58.com 365 城年度 ¥/㎡**（MIT、免登录、`curl` 直下、166KB），把它当作**城市级年度基准线/历史回填**；月度实时仍靠 creprice。指数校准用 NBS 70 城。

---

## 1. 候选清单表（实测城市数）

| # | 数据集 (owner/slug 或 repo) | 覆盖城市（**实测 distinct**） | 时间粒度/跨度 | 价格字段 | 是否绝对 ¥/㎡ | 行数 | 格式/大小 | 许可 | 获取（免登录?） | 新鲜度 |
|---|---|---|---|---|---|---|---|---|---|---|
| **1 ★最广** | GitHub `changao1/70-China-cities-housing-index-data-by-national-bureau-of-statistics` → `supplementary/58tongcheng_city_avg_price_annual_2010-2024.csv` | **365 城 / 32 省** | **年度** 2010–2024 | `price_yuan_per_sqm` | ✅ 是（¥/㎡） | 3447 | CSV / 104KB | **MIT** | ✅ `curl` raw 直下 | 2024 |
| **2 ★次广** | 同上 → `supplementary/anjuke_city_avg_price_annual_2015-2024.csv` | **349 城** | **年度** 2015–2024 | `price_yuan_per_sqm` | ✅ 是 | 3117 | CSV / 94KB | **MIT** | ✅ 同上 | 2024 |
| 3 | 同上 → `merged_housing_data_eng.csv`（NBS 70 城指数，主文件） | **70 城** | **月度** 2011-01–2026-05 | `new_home_price_index` / `existing_home_price_index`（环比,上月=100） | ❌ **指数非 ¥/㎡** | 12950 | CSV / 769KB | MIT | ✅ 同上 | 2026-05，GitHub Action 每月自动更新 |
| 4 | GitHub `hugohe3/70cityprice` → `70cityprice.csv` | **70 城**（含 ADCODE 行政区划码） | **月度** 2006–至今（≈4.5万条） | 多种指数（`CommodityHouseIDX`,`SecondHandIDX`… 同比/环比/定基比） | ❌ **指数非 ¥/㎡** | ≈45000 | CSV | 见仓库 | ✅ 同上 | 2026，一行命令自动更新 |
| 5 | Kaggle `chanemo/china-main-city-prices` | **10 城**（京沪穗深+成都/重庆/杭州/南京/苏州/武汉） | **单一截面 2021**（无时间列） | `price(Yuan/m²)` + `district` | ✅ 是（逐条挂牌） | 10×≈3000=29659 | 10×XLSX / 1.9MB | 见 Kaggle 页 | ✅ `curl` API 直下（无 token） | 2021（静态） |
| 6 | Kaggle `ruiqurm/lianjia`（前序已录） | **1 城**（北京，成交明细） | 月度 2011–2017（有 tradeTime） | `price`（成交 ¥/㎡） | ✅ 是 | ≈31.8万 | CSV / 12MB | CC BY-NC-SA 4.0 | ✅ | 2017 |
| 7 | Kaggle `vnvile/shanghai-second-hand-house-dataset`（前序） | **1 城**（上海） | 单月 ≈2023-10 | `listing_unit_price`(¥/㎡) | ✅ 是 | 5850 | Parquet / 2.6MB | MIT | ✅ | 2023-10 |

> 候选 1/2 是本轮**核心发现**：把覆盖从"3 城"直接拉到"366 城"。候选 3/4 是国家统计局 70 城**指数**（govstats 子任务的免境外-IP 替代数据源，但**不是 ¥/㎡**）。候选 5 把 Kaggle 上的绝对 ¥/㎡ 从 3 城扩到 10 城，但**无时间轴**。

---

## 2. 最广覆盖判定 & distinct 城市实证

### 2.1 58.com 365 城（候选 1）——本轮最广
- **实测**：`tail -n+2 58_city_avg.csv | cut -d, -f2 | sort -u | wc -l` → **365**。
- **省级覆盖 32 个**：上海 云南 内蒙古 北京 吉林 四川 天津 宁夏 安徽 山东 山西 广东 广西 新疆 江苏 江西 河北 河南 浙江 海南 湖北 湖南 甘肃 福建 西藏 贵州 辽宁 重庆 陕西 青海 香港 黑龙江。
- **城市样例（每 15 个抽 1，展示广度到县级市/边疆）**：七台河 临沧 仙桃 内江 双鸭山 咸阳 大庆 安顺 巴彦淖尔 张家口 抚顺 晋中 桂林 汕尾 济源 湘潭 玉溪 石家庄 苏州 西双版纳 连云港 酒泉 长治 青岛 黔东南。含拉萨/克拉玛依/三亚/西双版纳等边疆与非主流城市，**不是只有大城市**。
- **每年城市数**（覆盖随年份增厚）：2010=20、2015=215、2019=349、2023=364、2024=364。**2019 年起稳定在 349–364 城**。
- **面板深度**：214 城有 ≥10 年数据，49 城有满 14–15 年（2010–2024 全序列）。→ 不只是"某一年铺满"，主流城市有十余年**年度序列**。
- **价格合理性**（2024 年，抽查）：min 1874、max 58950 ¥/㎡；如克拉玛依≈5000、洛阳≈8800、上海≈2.2万起。量级正确，非脏数据。

### 2.2 anjuke 349 城（候选 2）——与 58 互补
- 实测 **349** distinct 城市；2015–2024 年度；同字段。
- 与 58.com 并集 = **366 城**（两平台高度重叠，anjuke 起始晚 5 年、少 16 城）。→ **以 58.com 为主，anjuke 做交叉校验/补缺**。

### 2.3 判定
> **是否有"全国 100+ 城市月度 ¥/㎡"免费数据集？没有。** 免费能拿到的最广绝对-价格数据是**年度**（58 城 365 / anjuke 349）；月度那档要么退化成 70 城**指数**，要么退化成单城明细。**"最广也就 366 城，且是年度、且是挂牌均价（非成交）"** —— 这是本项目在免费开放数据里能触到的天花板。

---

## 3. 各候选字段结构

**候选 1/2（58.com & anjuke，结构完全一致）**
```
province,city,year,price_yuan_per_sqm,yoy_pct
上海,上海,2010,22311,
河南,洛阳,2019,8556,11.51
新疆,克拉玛依,2024,5278,0.30
```
- `price_yuan_per_sqm` = 该城**当年二手房挂牌均价**（¥/㎡，整数）。`yoy_pct` 由价格自算的同比%（每城首年为空）。数据是从 58.com / anjuke 城市房价页抓的**年度聚合值**（README 明示 scraped，人工/半自动，非官方口径）。

**候选 3（NBS 70 城指数）**
```
city,year,month,new_home_price_index,existing_home_price_index,new_small_home_index,...(共10列)
Shanghai,2011,1,101.1,100.5,102.1,...
```
- 全是**环比指数（上月=100）**，无绝对价。适合做趋势/校准，**不能直接当 ¥/㎡ 落库**。

**候选 5（Kaggle 10 城，以北京为例，11 列）**
```
room, hall, bathroom, area(m²), direction, height, built, district(昌平/朝阳…), location(回龙观…), price(10k Yuan), price(Yuan/m²)
```
- 逐条挂牌，含 `district` + `price(Yuan/m²)`，**但无任何日期列** → 整份是 **2021 年单一截面**（描述："top 10 GDP cities in 2021, ~3000/city"）。可聚合出"10 城 × 区 × 一个 year_month(2021) 的挂牌均价 + sample_count"，无法成时间序列。

---

## 4. 映射到本项目模型（City→District, PriceSnapshot）

目标：`PriceSnapshot(region_type, region_id, year_month=YYYY-MM, supply/attention/value_price[¥/㎡], sample_count)`。

### 4.1 候选 1（58.com 365 城）→ 城市级年度基准（**首选导入**）
```
region_type   = city
region_id     = 用 city 名匹配现有 368 城目录（creprice）。366/368 基本可覆盖；需一张
                {csv城市名 → 项目 city_id} 对齐表（同名直匹配为主，少量异名人工核）。
year_month    = f"{year}-12"   # 年度值落到当年 12 月（或 06，需团队约定一个惯例）
supply_price  = price_yuan_per_sqm   # 挂牌均价 == 供给侧价格，语义对 supply_price
value_price   = 留空 / 或复用（标注 source=anjuke58_annual，避免与成交价曲线混淆）
sample_count  = NULL（源未给样本量）
data_source   = 'listing_annual_58' / 'listing_annual_anjuke'
```
- **产出**：一次导入即得**365 城 × 最多 15 个年度点**的历史价格曲线（主流城市十余年，长尾城 5–9 年）。这是把"城市地图从 3 城变全国"的最快路径。
- **注意口径**：挂牌价（非成交价），会略高于真实成交；且是年度点，**不能与 creprice 的月度成交/评估价放同一条线**，必须用 `data_source` 区分、前端标注"年度·挂牌"。

### 4.2 候选 2（anjuke 349 城）→ 同上，做**交叉校验/补缺**
- 同结构直接复用 4.1 的 ETL，`data_source='listing_annual_anjuke'`。两源同城同年可比对偏差；58 缺的城用 anjuke 补。

### 4.3 候选 3/4（NBS 70 城指数）→ 走 govstats 的 `price_index_snapshot`，**不进 ¥/㎡ 表**
- 与父任务 PRD 里 govstats 子任务一致：70 城月度指数。**价值**：候选 3/4 是**免境外 IP、GitHub 直下**的现成 NBS 指数 CSV，可绕开 govstats live 抓取被 403 阻塞的问题（见 DECISION.md）。用途：给 58/anjuke 的年度绝对价做**月度趋势插值/校准**（用指数把年度值内插到月度）。

### 4.4 候选 5（Kaggle 10 城 2021）→ 10 城 × 区 的单点快照
- 可聚合成 `region_type=district, year_month=2021-XX, supply_price=mean(price Yuan/m²), sample_count=count`。补齐 10 大城 2021 的一个区县级点，价值有限（广度已被候选 1 覆盖），可选。

---

## 5. 覆盖不足时的替代路线（已验证事实，非空谈）

1. **真正的"全国月度 ¥/㎡ 面板"存在，但需付费/非开放** —— 经管之家（pinggu.org）上有基于 anjuke 的整理数据集：
   - 「中国城市二手房房价历史数据 2010.1–2026.1」：**340 城，月度**，44753 条月度 + 4120 条年度，字段含行政区划代码/省/二手房均价(¥/㎡)/年均值/年中位数/年末价。**更新至 2026-01**。
   - 「安居客 626 城市二手房价数据 2010–2024.12」：**626 城，月度**，39994 条。
   - 均为论坛**收费附件（RMB）**，非免登录直下；来源同为 anjuke（与候选 2 同根，但月度、城市更多、更新）。→ 若要月度广覆盖且预算允许，这是唯一现成"面板"，否则得自采。

2. **国家统计局 70 城指数（权威、月度、免费）** —— 候选 3/4 已是现成 CSV（GitHub，免境外 IP）。**但是指数非 ¥/㎡**，且官方只有 70 城、只调查市辖区不含县。CEIC 另有 NBS「Property Price: YTD Avg」**省级**月度 ¥/㎡（RMB/sq m, 2003–2026），但只到**省**级（约 31 省）、且在 CEIC 付费库。

3. **live 自采（广度最大、但反爬/合规成本）**：
   - **anjuke.com/fangjia**、**58 同城城市房价页**：公开展示各城**历年 ¥/㎡**（候选 1/2 就是从这抓的年度聚合）。自己抓可拿**月度**且覆盖 300+ 城，但触发反爬与合规评估（延续项目串行限速红线）。
   - **creprice（禧泰 cityre.cn）**：项目现有源，城市/区/街镇**月度平均价**，2005 年起，全国覆盖，但正是当前限流/不稳定的源。
   - 结论：广度靠自采能到 300+ 城**月度**，但把不稳定/反爬问题从 creprice 换到 anjuke，未必更优。

4. **中指院 CREIS「百城价格指数」/ 贝壳研究院** —— 每月发布 **100 城新建 + 100 城二手 + 50 城租赁**指数（fdc.fang.com）。覆盖 100 城、月度、权威，但同样是**指数**且**无免登录批量 CSV**，需逐月页面抓或购买报告。

> 事实判断：**广度（300+ 城）与"月度 + 绝对 ¥/㎡ + 免费"三者，公开免费数据里无法同时满足。** 免费能拿的最佳组合是"**58.com 365 城年度 ¥/㎡（MIT，直下）**"作历史底图 + "**NBS 70 城月度指数**"作趋势校准；要月度绝对价的广覆盖，只能付费买 pinggu.org 面板或自采。

---

## 6. 获取命令（免登录，已实测）

```bash
# 候选 1/2/3：GitHub raw，直接下（无 token）
base="https://raw.githubusercontent.com/changao1/70-China-cities-housing-index-data-by-national-bureau-of-statistics/main"
curl -sL -o 58_city_avg.csv     "$base/supplementary/58tongcheng_city_avg_price_annual_2010-2024.csv"   # 365 城 年度 ¥/㎡
curl -sL -o anjuke_city_avg.csv "$base/supplementary/anjuke_city_avg_price_annual_2015-2024.csv"        # 349 城 年度 ¥/㎡
curl -sL -o nbs70_index.csv     "$base/merged_housing_data_eng.csv"                                     # 70 城 月度 指数

# 候选 5：Kaggle 公开集，302→签名 GCS，无需 kaggle.json
curl -sL -o china-main-city.zip "https://www.kaggle.com/api/v1/datasets/download/chanemo/china-main-city-prices"
unzip china-main-city.zip   # -> 10 个 *Prices.xlsx（京沪穗深/成都/重庆/杭州/南京/苏州/武汉，2021 单截面）
```

## 附：来源链接
- ★ changao1（58/anjuke 城市年度 ¥/㎡ + NBS 70 城月度指数，MIT）：https://github.com/changao1/70-China-cities-housing-index-data-by-national-bureau-of-statistics
- hugohe3 70 城指数（含 ADCODE，自动更新）：https://github.com/hugohe3/70cityprice
- Kaggle 10 城 2021 挂牌：https://www.kaggle.com/datasets/chanemo/china-main-city-prices
- 经管之家 340 城月度（付费，2010.1–2026.1）：https://bbs.pinggu.org/thread-16663249-1-1.html
- 经管之家 626 城月度（付费，2010–2024.12）：https://bbs.pinggu.org/thread-16536514-1-1.html
- 中指院 CREIS 百城指数：https://fdc.fang.com/index/ErShouFangIndex.html
- 安居客全国历年房价（自采源）：https://www.anjuke.com/fangjia/
- CEIC NBS 省级月度 ¥/㎡（付费库）：https://www.ceicdata.com/en/china/nbs-property-price-monthly
