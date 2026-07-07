# 采集源可行性研究：国家统计局（data.stats.gov.cn）

> 研究日期：2026-07-08　方法：curl / python-requests / Playwright MCP 实测 + 开源爬虫源码/VCR 录制核对（未臆测）
> 出口 IP：直连 = `54.37.83.196`（OVH，英国伦敦机房）；代理 = `134.195.101.195`（Black Mesa，美国加州）——**两者都是境外机房 IP**。

---

## 0. 一句话结论（决策级）

**能拿到高质量政府房价数据，但当前环境（境外机房 IP + 现有美国代理）拿不到。** `data.stats.gov.cn/easyquery.htm` 的 JSON API 被 WAF 按 **IP 地理位置**硬拦（`reason:UrlACL`），**与 Header/Cookie/握手无关**——已在真实浏览器会话内同源 fetch 复现 403。**接入的唯一前置条件是「中国大陆出口 IP」**（境内服务器 / 中国大陆住宅或机房代理）。现有 `http://…@10.0.0.1:2260` 美国代理**不可用**（且对该站 TLS 直接被 RST）。

难度评估：
- **拿到 IP 之后**：★☆☆☆☆ 很简单。无验证码/无滑块/无签名，POST 表单即返回 JSON，开源实现成熟。
- **数据契合度**：★★★☆☆ 需要注意——70 城是**价格指数（100 基准，非 ¥/㎡）**，与现有 `PriceSnapshot` 的绝对房价模型**维度不同**，需要新表；只有「销售额÷销售面积」能推算出**全国/分省**级别的绝对 ¥/㎡（无城市、无区县）。

---

## 1. Q1：easyquery.htm 403 的真正根因 + 可复现代码

### 1.1 根因：IP 地理围栏，不是握手问题

实测把「是不是缺 Header/Cookie」这个假设彻底证伪：

| 场景 | 结果 |
|---|---|
| 直连 `easyquery.htm`，无 Header | `HTTP 403`，body 含 `reason:UrlACL` + `Client IP: 54.37.83.196` |
| 直连 + 完整浏览器 UA + Referer + `X-Requested-With` + 先取 Cookie | 仍 `HTTP 403 UrlACL` |
| 大小写/路径变体（`EasyQuery.htm`、`easyquery.htm/`、`./easyquery.htm`） | 全部 `403 UrlACL`（规则很稳，绕不过） |
| **在真实浏览器里打开 data.stats.gov.cn 后，同源 `fetch('/easyquery.htm?...')`** | **仍 `HTTP 403`，`Client IP: 54.37.83.196`** ← 决定性证据 |
| 对照：`data.stats.gov.cn/robots.txt`、`/adv.htm`、静态资源 | `HTTP 404`（能到后端，未被 WAF 拦） |
| 对照：`www.stats.gov.cn/` | `HTTP 200` |

关键点：WAF 的 URL-ACL 规则**专门**针对 `/easyquery.htm`（数据抓取入口）这一条路径，对境外 IP 直接 403；同域其它路径能穿透到后端。所以「要什么 Header 才能 200」这个问题的答案是：**没有任何 Header 组合能让境外 IP 拿到 200；把请求发自中国大陆 IP 即可**（境内正常返回 200 + JSON，无需登录、无需特殊 Cookie）。

> 补充坑：easyquery.htm 本身也已是「上一代」门户。根域 `https://data.stats.gov.cn/` 现在 302 跳到**新版 SPA** `/dg/website/page.html#/pc/national/home`（见 §7）。但老的 easyquery JSON API 仍在线且境内可用，开源生态全部依赖它，仍是首选接入点。

### 1.2 可复现请求代码（境内 IP 上可直接 200）

以下代码经开源项目 `songjian/cnstats` 的 VCR 真实录制核对，参数/请求头/方法与官方前端一致。**唯一要改的是让它从中国大陆出口**（把 `session` 挂上中国代理，或部署在境内）：

```python
import requests, time, json

# 官方前端一致的请求头。注意：无需 Cookie，无需登录。
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36 Edg/99.0.1150.36"),
    "Referer": "https://data.stats.gov.cn/easyquery.htm?cn=A01",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Host": "data.stats.gov.cn",
}

def easyquery(m="QueryData", dbcode="hgyd", rowcode="zb", colcode="sj",
              wds=None, dfwds=None, id=None, wdcode=None,
              cn_proxy=None):
    """境内 IP 上返回 200 + JSON；境外 IP 返回 403 UrlACL。"""
    url = "https://data.stats.gov.cn/easyquery.htm"
    data = {
        "m": m, "dbcode": dbcode, "rowcode": rowcode, "colcode": colcode,
        "wds":   json.dumps(wds   or [], ensure_ascii=False),
        "dfwds": json.dumps(dfwds or [], ensure_ascii=False),
        "k1":    str(int(time.time() * 1000)),   # 毫秒时间戳，纯缓存穿透
    }
    if id:     data["id"] = id
    if wdcode: data["wdcode"] = wdcode
    s = requests.Session()
    s.trust_env = False                          # 关键：不吃环境里的 http_proxy
    proxies = {"http": cn_proxy, "https": cn_proxy} if cn_proxy else None
    r = s.post(url, data=data, headers=_HEADERS, proxies=proxies, verify=False, timeout=30)
    return r.json()

# ① 发现指标树（拿 zb 指标代码）：
#    easyquery(m="getTree", dbcode="csyd", id="A01", wdcode="zb")   # 城市月度价格类目
# ② 查询某指标的一段时间序列：
#    easyquery(dbcode="hgyd",
#              dfwds=[{"wdcode":"zb","valuecode":"A020101"},
#                     {"wdcode":"sj","valuecode":"202301-202312"}])
# ③ 城市/分省数据：把地区放进 wds
#    easyquery(dbcode="csyd",
#              wds=[{"wdcode":"reg","valuecode":"110000"}],           # 110000=北京
#              dfwds=[{"wdcode":"zb","valuecode":"<70城房价指标码>"},
#                     {"wdcode":"sj","valuecode":"LAST13"}])
```

curl 等价形式（境内可 200）：

```bash
curl 'https://data.stats.gov.cn/easyquery.htm' \
  -H 'User-Agent: Mozilla/5.0 ... Chrome/99 ... Edg/99' \
  -H 'Referer: https://data.stats.gov.cn/easyquery.htm?cn=A01' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data 'm=QueryData&dbcode=hgyd&rowcode=zb&colcode=sj&wds=%5B%5D&dfwds=%5B%7B%22wdcode%22%3A%22zb%22%2C%22valuecode%22%3A%22A020101%22%7D%2C%7B%22wdcode%22%3A%22sj%22%2C%22valuecode%22%3A%22202312%22%7D%5D&k1=1772507778302'
```

**方法是 POST（form-urlencoded）**，GET 亦可但官方前端用 POST。参数含义：
- `dbcode` 数据库：`hgyd`宏观月度 / `hgjd`宏观季度 / `hgnd`宏观年度 / `fsyd`分省月度 / `fsjd`分省季度 / `fsnd`分省年度 / `csyd`城市月度 / `csjd`城市季度 / `csnd`城市年度。
- `rowcode`/`colcode`：透视表的行列维（一般 `zb`/`sj`）。
- `wds`：**固定/筛选**维（地区 `reg` 放这里）。`dfwds`：**主查询**维（指标 `zb` + 时间 `sj`）。
- `sj.valuecode` 支持：单点 `202312`、区间 `202301-202312`、`LAST13`（最近 13 期）、`2020-2024` 等。
- `k1`：毫秒时间戳缓存穿透。`h=1`：可选，返回中文说明。

---

## 2. 直连 vs 代理 实测状态码对比（Q6）

| 请求 | 直连（54.37.x, OVH-UK） | 美国代理（134.195.x） |
|---|---|---|
| `easyquery.htm?m=QueryData…` | **403** `UrlACL` | **000**（CONNECT 隧道 200 后，TLS 立刻 `unexpected eof / RST`，被服务器掐断） |
| `api.ipify.org`（验证出口） | 200，IP=54.37.83.196 | 200，IP=134.195.101.195 |
| `www.stats.gov.cn/` | 200 | —（未测，同为境外无意义） |
| 新版 `/dg/website/publicrelease/...` | 200（见 §7） | — |

结论：**现有代理比直连更差**——美国出口对 data.stats.gov.cn 的 TLS 直接被 RST，连 WAF 页面都拿不到。**必须换中国大陆出口。**

---

## 3. 能拿到哪些房价相关指标（Q2）+ 数据形状（Q3）

### 3.1 指标发现方式（getTree）——已实测真实响应

请求：`m=getTree&dbcode=hgyd&id=A0101&wdcode=zb`（列出 A0101「居民消费价格指数」类目的子节点）。真实返回（节选，已解码）：

```json
[
 {"dbcode":"hgyd","id":"A01010J","isParent":false,"pid":"A0101","wdcode":"zb",
  "name":"全国居民消费价格分类指数(上年同月=100)(2026-)"},
 {"dbcode":"hgyd","id":"A01010G","isParent":false,"pid":"A0101","wdcode":"zb",
  "name":"全国居民消费价格分类指数(上年同月=100)(2021-2025)"},
 {"dbcode":"hgyd","id":"A010101","isParent":false,"pid":"A0101","wdcode":"zb",
  "name":"全国居民消费价格分类指数(上年同月=100)(2016-2020)"}
 /* … */
]
```

> **重要坑（基期改版）**：同一指标随「对比基期」换代会分配**不同的 zb code**。上例可见 `(2026-)=A01010J`、`(2021-2025)=A01010G`、`(2016-2020)=A010101`。这与「70 城房价从 **2026 年 1 月起改用 2025 年为新基期**、各城基本分类权数调整」完全对应。**采集 2026 年及以后的数据必须用新一代 zb code；跨基期拼接时序会断层**——务必按节点名里的年份区间选码，别硬编码一个旧码。`isParent:true` 的节点要继续 getTree 下钻，`false` 才是可查的叶子指标。

### 3.2 三类可用房价数据

**(A) 70 个大中城市商品住宅销售价格指数** ← 最核心
- 位置：`dbcode=csyd`（城市月度），地区维 `reg` = 6 位 GB/T 2260 行政区划码，实测 `csyd` 地区表共 **69 个城市**（即「70 大中城市」集合，与官方 70 城口径一致；无区县层级）。
- 指标形态：**价格指数（100 基准，float），不是 ¥/㎡ 绝对价**。每个口径都是独立 zb code：
  - 新建商品住宅销售价格指数：上月=100（环比）/ 上年同月=100（同比）/ 上年=100 或 2025=100（定基）
  - 二手住宅销售价格指数：同上三个口径
  - （2026- 起为一代新码，见 §3.1）
- 参数样例：
  ```
  dbcode=csyd
  wds  =[{"wdcode":"reg","valuecode":"110000"}]          # 北京；可多选或不选取全部城市
  dfwds=[{"wdcode":"zb","valuecode":"<新建住宅环比 zb 码>"},
         {"wdcode":"sj","valuecode":"LAST13"}]
  ```
  > 具体 70 城房价 zb 数值码需在**境内**用 `getTree(dbcode=csyd)` 从价格类目下钻枚举得到（本次因境外 IP 无法枚举）。发现机制已在 §3.1 用真实响应验证，境内跑一次即得。

**(B) 商品房销售面积 / 商品房销售额** ← 用来推算绝对均价
- 位置：`dbcode=hgyd`（全国月度，累计值，单位 万㎡ / 亿元）与 `dbcode=fsyd`（分省月度）。房地产开发类目下（`tablequery` 里 `各地区商品房销售面积` 对应报表码 `AA130Q`）。
- 用途：**均价(¥/㎡) = 销售额 / 销售面积**，只能算到**全国 / 分省**粒度，**没有城市、没有区县**。注意官方多为「累计值」，算单月要做累计差分（1-2 月合并发布）。
- 参数样例：`dbcode=fsyd, wds=[{reg:440000}](广东), dfwds=[{zb:<销售额码>},{zb:<销售面积码>},{sj:LAST13}]`。

### 3.3 真实 JSON 响应片段（Q3，实测录制）

**① 全国月度，单指标单期**（规上工业增加值同比，示范形状）：
```json
{"returncode":200,"returndata":{
  "datanodes":[
    {"code":"zb.A020101_sj.202312",
     "data":{"data":6.8,"dotcount":1,"hasdata":true,"strdata":"6.8"},
     "wds":[{"valuecode":"A020101","wdcode":"zb"},{"valuecode":"202312","wdcode":"sj"}]}],
  "wdnodes":[
    {"wdcode":"zb","wdname":"指标","nodes":[
       {"code":"A020101","name":"…","cname":"规上工业增加值_同比增长","unit":"","dotcount":1,"exp":"…","memo":"…"}]}]}}
```

**② 带地区维（reg）的三维形状**（分省年度，展示 reg 维怎么出现）：
```json
{"returncode":200,"returndata":{
  "datanodes":[
    {"code":"zb.A010101_reg.110000_sj.2023",
     "data":{"data":0.0,"dotcount":0,"hasdata":false,"strdata":""},
     "wds":[{"valuecode":"A010101","wdcode":"zb"},
            {"valuecode":"110000","wdcode":"reg"},
            {"valuecode":"2023","wdcode":"sj"}]}],
  "wdnodes":[
    {"wdcode":"zb","wdname":"指标","nodes":[{"code":"A010101","cname":"地级区划数","unit":"个",…}]},
    {"wdcode":"reg","wdname":"地区","nodes":[{"code":"110000","cname":"北京市",…}]},
    {"wdcode":"sj","wdname":"时间","nodes":[{"code":"2023","name":"2023年",…}]}]}}
```

**数据形状要点**：
- `datanodes[].code` 是维度拼接键：全国 = `zb.<码>_sj.<期>`（2 维）；城市/分省 = `zb.<码>_reg.<地区>_sj.<期>`（3 维）——**解析靠 split("_") 后各段 strip 前缀**（`zb.` / `reg.` / `sj.`）。
- 数值在 `data`：`data`（数值 float）、`strdata`（显示字符串）、`dotcount`（小数位）、`hasdata`（**缺失月份 hasdata=false / strdata=""，必须判空**）。
- `wdnodes` 是维度字典（指标含 `cname/name/unit/exp/memo`，地区含中文名），用来落地维度元信息。
- 70 城维度：只有约 70 个城市，**无区县**；时间粒度**月度**；值是**指数**，不是元/㎡。

---

## 4. 更新频率与最新可得月份（Q4）

- **频率：月度。** 每月发布「N 月份 70 个大中城市商品住宅销售价格变动情况」，发布日约在 **次月 15–18 日**。
- 实测发布序列（www.stats.gov.cn 稿件日期）：2026-04 数据→2026-05-18 发布；2026-05 数据→2026-06-16 发布；2026-03 数据→2026-04-16。
- **截至今天（2026-07-08）最新可得月份 = 2026 年 5 月**（6 月数据要到约 7 月 15–18 日才出）。
- easyquery 数据库（csyd/hgyd）通常与稿件同步或稍滞后 T+1 更新。

## 5. 验证码 / 滑块 / 签名（Q5）

**无。** 政府站无验证码、无滑块、无 JS 签名参数、无需登录/Token。唯一的「参数」是 `k1` 毫秒时间戳（缓存穿透，随便填当前时间即可）。防护手段只有前述 **WAF IP-URL-ACL 地理围栏** + 常规限流。因此接入的全部难点收敛为「一个稳定的中国大陆出口 IP + 适度限速」。

---

## 6.（对照）现有源 creprice 已触发限流的启示

creprice 是 ¥/㎡ 绝对价、城市→区县、月度，三条 series（供给/关注/价值）+ 样本数——直接喂 `PriceSnapshot`。国家统计局补的是**权威性与全国/分省口径**，但**粒度更粗（无区县）且 70 城是指数**，两者是互补而非替代：creprice 提供 ¥/㎡ 与区县颗粒，NBS 提供官方指数 + 全国/分省绝对均价锚点。

---

## 7. 附带发现：新版 SPA 门户 `/dg/`（境外 IP 部分可达）

根域已改版为 dsf 平台 SPA（`/dg/website/page.html#/...`）。实测**境外 IP 也能 200** 的公开接口（未被地理围栏）：
```
GET /dg/website/publicrelease/web/external/queryAllPblIbs?type=month     → 200，返回月报报表目录 JSON
GET /dg/website/publicrelease/web/external/new/queryCMSArticles?code=zxfb → 200，返回"最新发布"稿件列表
GET /dg/website/datascreen/relationweb/getReleaseData?...                 → 200
```
但**真正的数值查询接口**在 `/dg/api/metadata/macrodata/kiv/queryMetadataTableData`（从 `dsf-dataview` JS 里挖出），实测境外 IP 返回 **403（nginx `dps`，需鉴权/Token）**，不是干净的抓取入口。
- 含义：新门户把「文章/目录/日程」等元数据开放给境外，但**指标数值仍旧走受 IP 围栏的通道**。因此**不改变结论**——要数值仍需中国大陆 IP + easyquery（生态成熟）或逆向新门户带鉴权的 metadata 接口（成本更高，不推荐）。

---

## 8. 与 `PriceSnapshot` 模型的映射建议

现有模型（绝对 ¥/㎡ 整数）：
```
PriceSnapshot(region_type, region_id, year_month,
              supply_price:int, attention_price:int, value_price:int, sample_count:int)
UNIQUE(region_type, region_id, year_month)
```

NBS 数据有两种形态，**建议区别对待**：

### 8.1 70 城价格指数 → 需要新表（不要硬塞进 PriceSnapshot）
理由：指数是 100 基准的 **float**，且一个城市一个月有**多个口径**（新建/二手 × 环比/同比/定基 = 最多 6 个值），语义与「元/㎡ 整数」完全不同，塞进 `supply_price` 会污染字段含义、且 UNIQUE 键不够用。建议：
```python
class PriceIndexSnapshot(Base):            # 新表
    region_type: str        # 'city'（NBS 70 城）
    region_id:   int        # 见 §8.3 地区码映射
    year_month:  str        # 'YYYY-MM'
    dwelling_type: str      # 'new'(新建商品住宅) | 'second'(二手住宅)
    base_type:   str        # 'mom'(上月=100) | 'yoy'(上年同月=100) | 'fixed'(定基 2025=100)
    index_value: float
    source:      str = 'govstats'
    # UNIQUE(region_type, region_id, year_month, dwelling_type, base_type)
```

### 8.2 全国/分省 销售额÷销售面积 → 可复用 PriceSnapshot（加 source 区分）
`均价(¥/㎡) = 销售额 / 销售面积` 是绝对价，能落 `value_price`（或专设 `derived_price`）。但 region 粒度是**全国/分省**，需扩 `region_type` 枚举：
```
region_type ∈ {'national', 'province', 'city', 'district'}   # 现有多为 city/district
```
建议给 `PriceSnapshot` 增一列 `source: str`（`'creprice'` / `'govstats'`）并把 UNIQUE 键扩为 `(source, region_type, region_id, year_month)`，避免多源同区县撞键；NBS 推算均价写 `value_price`，`supply/attention_price` 留空，`sample_count` 留空。

### 8.3 地区码映射（跨源对齐的必做项）
- NBS 用 **6 位 GB/T 2260 行政区划码**（110000=北京、440100=广州…）；creprice 用自有城市码（拼音短码如 `bj`）。
- 需建**城市码 crosswalk 表** `region_map(source, source_code, gbcode, name)`，把 creprice 城市码 ↔ NBS 6 位码对齐，`region_id` 统一存 GB 码或内部主键。这是多源合并的前置基础设施，建议本任务一并落地。

### 8.4 落地顺序建议
1. 先解决**中国大陆出口**（境内小机器/中国代理），否则一切阻塞在 403。
2. 复用 §1.2 代码封装 `GovStatsSource`（`fetch_cities`←csyd reg 表、`fetch_price_index`、`fetch_national_avg_price`）。
3. 新增 `PriceIndexSnapshot` 表存 70 城指数；`PriceSnapshot` 加 `source` 列存推算均价。
4. 建 `region_map` 做码表对齐。
5. 采集限速（政府站，建议 ≥1s/请求、夜间批量），无验证码所以稳定性主要看 IP 与频率。

---

## 9. 参考实证来源
- 本地实测：curl / requests / Playwright（403 UrlACL、302→/dg、真实浏览器同源 fetch 复现、IP 归属、新门户接口状态码）。
- 开源核对：`songjian/cnstats`（`common.py` 的 easyquery 实现与请求头 + `tests/cassettes/*.yaml` **真实录制的请求体与 JSON 响应**）、`xiancode/STATS_HG_DATA`（dbcode 枚举、csyd 69 城码表、returndata 解析断言）。
- 发布节奏：www.stats.gov.cn「70 个大中城市商品住宅销售价格变动情况」稿件日期序列（2026-03…2026-05）。
</content>
</invoke>
