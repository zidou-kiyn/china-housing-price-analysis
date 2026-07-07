# Kaggle / 公开数据集调研：中国城市房价历史回填

> 任务：为「多源采集与数据源切换」寻找可用于中国城市房价历史回填的现成公开数据集。
> 调研日期：2026-07-08。所有 Kaggle 链接均已实测直连可达（HTTP 200），元数据经 Croissant JSON-LD 提取，非凭记忆。

---

## 0. 结论速览（TL;DR）

- **最推荐首选：`ruiqurm/lianjia`（北京 2011–2017，约 31.8 万条链家成交记录）** —— 唯一一个自带**成交日期 + 区县编码 + ¥/㎡ 单价**的大样本历史数据集，可直接聚合成我们「城市/区县 × 月度 × ¥/㎡ + sample_count」模型，用于**北京的真实历史时间序列回填**。
- **当期快照补充：`vnvile/shanghai-second-hand-house-dataset`（上海，5850 条，含 district/sub_district + listing_unit_price ¥/㎡，MIT 许可）** —— 适合回填上海的**单月快照**（约 2023-10），字段最规整、许可最宽松。
- **重要获取结论**：这些**公开** Kaggle 数据集**无需 kaggle.json / 无需登录**即可用 `curl -L` 直接下载 —— `https://www.kaggle.com/api/v1/datasets/download/{owner}/{slug}` 会 302 跳转到已签名的 GCS 直链，实测返回真实 zip（206 + application/zip）。Kaggle API token 仅在批量/私有场景才需要。
- **根本性局限**：所有候选都是**逐条房源/成交明细的静态历史快照**，没有一个是预聚合好的「城市月度 ¥/㎡」时间序列。要进我们的 `PriceSnapshot`，必须自己按 (city, district, year_month) 做 GROUP BY 聚合。除北京数据集外，其余多为**单一时点截面**（无跨年月份维度），只能填一个 `year_month`。全部数据新鲜度截止 2017–2023，**无当前值**，不能替代 creprice 的实时性，只能做历史回填/交叉校验。

---

## 1. 数据集清单表

| # | 数据集 (owner/slug) | 标题 | 覆盖 | 关键字段 | 格式/大小 | 许可 | 获取方式 |
|---|---|---|---|---|---|---|---|
| 1 ★ | `ruiqurm/lianjia` | Housing price in Beijing | **北京**全市；成交时间 **2011–2017**（少量 2018-01 及 2009/2010）；**约 31.8 万行** | `tradeTime`(成交日期), `district`(区县编码 1–13), `price`(**¥/㎡ 单价**), `totalPrice`(总价,万), `square`(面积), `communityAverage`(小区均价), `Lng/Lat`, `followers`, `DOM`, 户型/楼层/结构等共 **26 列** | CSV (`new.csv`)，archive.zip **12.4 MB** | **CC BY-NC-SA 4.0**（署名-非商业-相同方式共享） | 无需登录：`curl -L .../download/ruiqurm/lianjia` |
| 2 ★ | `vnvile/shanghai-second-hand-house-dataset` | Shanghai Second-Hand House Dataset | **上海**二手房；截面快照（`insert_time`≈**2023-10**）；**5850 行** | `district`(浦东…), `sub_district`(张江…), `community_name`, `listing_unit_price`(**¥/㎡**), `listing_total_price`(万), `market_eval_price`(评估价 ¥/㎡), `area`, `latitude/longitude`, `year_built`, `layout_raw`, 物业费/容积率/绿化率/挂牌标签等共 **43 列** | **Parquet**(`dataset.parquet`)，archive.zip **2.56 MB** | **MIT**（最宽松，可商用） | 无需登录：`curl -L .../download/vnvile/shanghai-second-hand-house-dataset` |
| 3 | `lianghaoxun/shenzhen-housing-price-dataset` | Shenzhen Housing Price Dataset | **深圳**各区；描述「爬取 **2022 年**深圳市各区数据」；小样本 | Excel 表（字段未在元数据暴露；含区/价格等，需下载后确认） | **XLS** (application/vnd.ms-excel)，archive.zip **536 KB** | **Unknown（未声明）** — 慎用，不建议商用/再分发 | 无需登录：`curl -L .../download/lianghaoxun/shenzhen-housing-price-dataset` |
| 4 | `chengzhuzhang/transformed-beijing-housing-price-from-lianjia` | Transformed Beijing Housing Price from Lianjia | **北京**（源自 ruiqurm，已为回归建模转换） | `new BJ house.csv`(28 列：totalPrice/price/square/tradeTime 数值化 + one-hot) + 两个 stepAIC 设计矩阵(49 列，含交互项) | CSV×3，archive.zip **71.5 MB** | **Apache 2.0** | 无需登录同上 |
| 5 | GitHub Gist `dongxiahe/eae8bc296511af6758f2` | 中国全国房价 since 2000 | **全国口径**（非城市），**年度 2000–2013**，仅 6 行 | 年份 × {商品房/住宅/别墅/写字楼…均价 ¥/㎡}，分号分隔、逗号做小数点 | CSV，<1 KB | 无声明（Gist） | `curl -L https://gist.githubusercontent.com/dongxiahe/eae8bc296511af6758f2/raw` |

补充（非静态数据集，作背景/扩展来源，需自己跑或受限）：

| 来源 | 说明 | 适用性 |
|---|---|---|
| `github.com/jumper2014/lianjia-beike-spider` | 链家/贝壳爬虫，覆盖**北上广深等 21 城**（小区/二手房/出租/新房），输出 CSV/MySQL/Mongo | **多城市**结构最贴合，但是**爬虫非数据集**：需自行运行，产出为**当期快照**，且触及采集合规问题 |
| `github.com/sczhengyabin/Lianjia_House_Info` | 链家二手房信息+成交记录爬虫，含成都示例数据 | 同上，示例数据可参考字段 |
| Kaggle 竞赛 `china-real-estate-demand-prediction` | 「中国首个房地产需求预测挑战」，城市/板块级需求数据 | 城市粒度，但**需接受竞赛规则后才能下载**（非开放直链），且目标是需求量而非 ¥/㎡ 均价 |
| NBS 70 城房价指数 / FRED `QCNN368BIS` | 官方 70 大中城市月度房价**指数**（非绝对 ¥/㎡） | 权威、月度、覆盖广，但为**指数**（环比/同比），非我们要的 ¥/㎡ 绝对值；未见规整 Kaggle CSV，需从 NBS/CEIC/FRED 取 |

---

## 2. 各数据集字段结构详情

### 2.1 `ruiqurm/lianjia`（★ 首选，北京 26 列）
```
url, id, Lng, Lat, Cid(小区ID), tradeTime(成交日期), DOM(在市天数),
followers(关注人数), totalPrice(总价,万元), price(成交单价, 元/㎡),
square(建筑面积,㎡), livingRoom, drawingRoom, kitchen, bathRoom,
floor, buildingType, constructionTime(建成年), renovationCondition(装修),
buildingStructure(结构), ladderRatio(梯户比), elevator, fiveYearsProperty(满五),
subway(近地铁), district(区县编码 1–13), communityAverage(小区均价, 元/㎡)
```
- `price` = **成交单价（元/㎡）**，正是我们要的 ¥/㎡；`tradeTime` 提供月份维度；`district` 是 1–13 整数编码（需一张「编码→北京区县名」映射表，公开 notebook 里普遍有；下载后可据经纬度/小区反查校准）。
- 数据来源 `bj.lianjia.com/chengjiao`（成交页），即**真实成交价**而非挂牌价。

### 2.2 `vnvile/shanghai-second-hand-house-dataset`（★ 上海 43 列，节选）
```
id, house_id, community_id, community_name, district(浦东), sub_district(张江),
listing_total_price(挂牌总价,万), listing_unit_price(挂牌单价, 元/㎡),
market_eval_price(市场评估价, 元/㎡), area(㎡), layout_raw(2室2厅1卫),
room_count, hall_count, toilet_count, orientation, floor_location, total_floors,
year_built, renovation, building_type, latitude, longitude, insert_time(≈2023-10),
subway_info, property_fee, plot_ratio, greening_rate, total_households,
title, selling_points, tags, ...图片URL..., agent_*, url, crawl_ts
```
- `listing_unit_price` = **挂牌单价（元/㎡）**；`district` + `sub_district` 天然对应我们的「城市→区县（→更细板块）」。注意是**挂牌价**（非成交价），会略高于成交价。

### 2.3 `chengzhuzhang/...transformed...`（北京，衍生建模用）
`new BJ house.csv`：`totalPrice, price, Lng, Lat, square, livingRoom, drawingRoom, kitchen, bathRoom, tradeTime, constructionTime, followers, ladderRatio, elevator, subway, buildingType, renovationCondition, lasting, totalRoom` + buildingType/renovation 的 one-hot + `totalPrice_log_std`。
—— 已为回归标准化/独热，`tradeTime` 被数值化，**不利于直接按月聚合**，故不作导入首选，仅当北京数据的辅助特征来源。

---

## 3. 获取方式（可操作）

**方式 A — 免登录直链（推荐，已实测）**
```bash
# 无需 kaggle.json，无需账号；302 跳转到已签名 GCS 直链，返回真实 zip
curl -L -o beijing.zip \
  "https://www.kaggle.com/api/v1/datasets/download/ruiqurm/lianjia"
unzip beijing.zip          # -> new.csv
# 上海同理：
curl -L -o shanghai.zip \
  "https://www.kaggle.com/api/v1/datasets/download/vnvile/shanghai-second-hand-house-dataset"
```
> 若项目所在网络对 Kaggle/GCS 有限制，可挂题面给的美国出口代理：`-x http://Default:...@10.0.0.1:2260`。

**方式 B — Kaggle CLI（批量/需要稳定重跑时）**
```bash
pip install kaggle
# ~/.kaggle/kaggle.json 放入 Kaggle 账号 Settings→API 生成的 token（{"username","key"}）,chmod 600
kaggle datasets download -d ruiqurm/lianjia
```
- 元数据（列/许可/文件大小）可免登录抓 Croissant：`.../datasets/{owner}/{slug}/croissant/download`（本报告即由此提取）。
- Gist 全国 CSV：`curl -L https://gist.githubusercontent.com/dongxiahe/eae8bc296511af6758f2/raw`。

---

## 4. 映射到本项目模型（City→District, PriceSnapshot, PriceDistribution）

我们的目标表：`PriceSnapshot(region_type, region_id, year_month=YYYY-MM, supply_price/attention_price/value_price[¥/㎡], sample_count)` + `PriceDistribution(价格区间分布)`。候选数据集都是**逐条明细**，需一层**聚合 ETL**。

### 4.1 首选：北京 `ruiqurm/lianjia` → 北京 city + district 月度时间序列
逐条 → 分组聚合：
```
year_month   = tradeTime 截取到 YYYY-MM
分组键        = (region_type, region_id, year_month)
              region_type=district 时按 district 编码分组；region_type=city 时全北京汇总
value_price   = mean(price)             # price 为成交单价 元/㎡  -> 直接落 value_price
sample_count  = count(*)                # 该城市/区县该月成交笔数
attention_price ≈ mean(price weighted by followers) 或 mean(communityAverage)  # 近似
supply_price  ≈ 无直接对应（数据是成交价，非挂牌供给价）→ 建议留空或复用 value_price 并标注 source
PriceDistribution = 按 price 分桶(如 <3w,3-5w,5-8w,8-10w,>10w 元/㎡) 统计各 year_month 占比
```
- 需一张 `district(1–13) → 北京区县名/我们的 district_id` 映射表（人工核对一次即可，可借经纬度落到区）。
- 产出：北京 2011–2017 **约 84 个月 × 十余区** 的真实历史序列 —— 直接补齐历史曲线。

### 4.2 上海 `vnvile/...`（单月快照）→ 上海 city + district 的一个 `year_month`
```
year_month   = insert_time 的月份（≈ 2023-10，单一值）
region        = district(→city), sub_district 可作更细板块（超出现有两级，可先并到 district）
value_price   = mean(market_eval_price)     # 评估价更接近成交价
supply_price  = mean(listing_unit_price)    # 挂牌单价 == 供给价，正好对上 supply_price!
sample_count  = count(*)
PriceDistribution = listing_unit_price 分桶
```
- 上海数据**同时含挂牌价(供给)与评估价**，是唯一能同时喂 `supply_price` 与 `value_price` 的源；但只有一个月，无法成序列。

### 4.3 深圳 / 全国 Gist
- 深圳 2022 xls：下载后确认列，若含区+单价，按 4.2 方式填 2022 的一个 `year_month`（region_type=city/district）。许可未知，仅内部历史校验、勿再分发。
- 全国 Gist：只有全国口径年度均价（2000–2013），可作 `region_type=city` 之外的「全国基准线」或缺城市时的兜底趋势，**不落区县**。

**最适合直接导入排序**：① 北京 `ruiqurm/lianjia`（有时间轴、样本大、正是成交 ¥/㎡）＞ ② 上海 `vnvile`（字段规整、许可宽松、供给+价值双价）＞ ③ 深圳 ＞ 全国 Gist ＞ Transformed（不建议直接导）。

---

## 5. 局限与风险（决策必读）

1. **静态历史，非实时** —— 新鲜度截止：北京 2017（+零星 2018-01）、上海 ≈2023-10、深圳 2022、全国 Gist 2013。**都不能替代 creprice 提供当前值**，定位是「历史回填 + 交叉校验」，不是新采集源。
2. **无预聚合月度序列** —— 全部是逐条明细，必须自建聚合 ETL；除北京外均为**单时点截面**，一个数据集只能贡献一个 `year_month`，无法构成时间序列。
3. **口径不统一** —— 北京是**成交单价**、上海是**挂牌价/评估价**、深圳未知、Gist 是全国口径。跨源拼接时 `supply/attention/value_price` 的语义要逐源标注 `data_source`，避免把挂牌价和成交价混为同一条曲线。
4. **区县编码/命名需人工对齐** —— 北京 district 是数字编码；上海是中文区名+板块（板块比我们两级更细）。导入前需维护映射表。
5. **许可约束** —— 北京 CC BY-NC-SA 4.0（**非商业**、需署名、衍生同协议）；深圳 **许可未声明**（合规风险最高，勿商用/再分发）；上海 MIT、Transformed Apache 2.0（较自由）。若系统对外商用，优先 MIT/Apache 源，北京数据注明署名与非商业。
6. **样本偏差** —— 均为链家/贝壳单一中介的房源，非全市场；小区/高价盘可能过采样，均值会偏离官方口径。建议用 NBS 70 城指数做趋势校准。
7. **覆盖城市有限** —— 现成静态数据集集中在北京/上海/深圳三城；要覆盖题述「21 城」需转向 `jumper2014/lianjia-beike-spider` 自采（当期快照 + 合规评估），或接 NBS/FRED 指数。

---

## 附：数据来源链接
- Kaggle 北京：https://www.kaggle.com/datasets/ruiqurm/lianjia
- Kaggle 上海：https://www.kaggle.com/datasets/vnvile/shanghai-second-hand-house-dataset
- Kaggle 深圳：https://www.kaggle.com/datasets/lianghaoxun/shenzhen-housing-price-dataset
- Kaggle 北京(transformed)：https://www.kaggle.com/datasets/chengzhuzhang/transformed-beijing-housing-price-from-lianjia
- 全国 Gist：https://gist.github.com/dongxiahe/eae8bc296511af6758f2
- 21 城爬虫：https://github.com/jumper2014/lianjia-beike-spider
- 链家爬虫(多城/成都示例)：https://github.com/sczhengyabin/Lianjia_House_Info
- Kaggle 竞赛(需求预测)：https://www.kaggle.com/competitions/china-real-estate-demand-prediction
- NBS 70 城指数(FRED)：https://fred.stlouisfed.org/series/QCNN368BIS
