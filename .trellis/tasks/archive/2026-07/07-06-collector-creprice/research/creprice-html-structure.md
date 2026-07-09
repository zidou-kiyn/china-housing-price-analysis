# Research: creprice.cn 真实 HTML / 数据结构实测

- **Query**: 实测 creprice.cn 的城市列表页、城市均价时序页、区县均价页的真实 HTML 结构，为爬虫解析器提供准确样本
- **Scope**: external（实测抓取 creprice.cn 线上页面 + JS + API）
- **Date**: 2026-07-06
- **抓取环境**: Python 3.11.11 + requests 2.34.2；所有页面 `Content-Type: text/html; charset=utf-8`（UTF-8，无 GBK 问题）

---

## 0. 最关键结论（先读这一条）

**城市/区县均价页（`/urban/*.html`、`/district/*.html`）没有任何 `<table>` 标签。** 页面是
**Vue + ECharts + ElementUI 的客户端渲染 SPA**，所有价格时序、价格分布、区县均价数据都是页面
加载后由 JavaScript 通过 **JSON API** 异步拉取的，静态 HTML 里的图表容器（`chart_price_cont` 等）
**全是空的**。

> `requests` 直接抓 `/urban/qz.html` 拿不到任何价格数字。

因此爬虫解析器**不应该解析 HTML 表格**，而应该：

1. 用 `requests` 抓 **静态页**只为拿到服务端注入的 `paramsphp` 配置（含 `cityCode`、`distCode`、
   `lastMonth`、`propType` 等）——或者干脆跳过，直接用城市列表页得到的 code。
2. 直接请求 **JSON API**（同源 `https://creprice.cn/market/*.html`）拿结构化数据。

只有**城市列表页 `/rank/citySel.html` 是真正的静态 HTML**（城市/区县链接直接在 HTML 里），需要 HTML 解析。

**响应未加密**：虽然页面引入了 `jsencrypt.min.js` + `base64.js`，但价格 API 走普通 jQuery `$.ajax`
（`dataType:json`），返回明文 JSON。base64 只用于 `paramsphp.source` / `moniSearchStr` 这类参数打包，
与价格数据解密无关。

**请求头要求**：裸 `requests`（无 User-Agent）会在 TLS 层被服务器直接断开（SSLError）；
**带任意浏览器 User-Agent 即可成功**（200），**不需要 Referer / Cookie / 登录**（匿名可取数）。

---

## 1. 城市列表页 `https://creprice.cn/rank/citySel.html`

### 1.1 概况

- 静态 HTML，348630 字节，**城市/区县链接全部在静态 HTML 中**（虽保留 Vue 的 `@click` / `v-if` 属性，
  但数据已服务端渲染进 HTML，`requests` 可直接解析）。
- 整页只有 2 个 `<table>`（与城市列表无关）。

### 1.2 城市链接结构

```html
<a class="city pr0" @click="addUsedCity('aq','','安庆')" href="/city/aq.html">安庆</a>
<a class="city "    @click="addUsedCity('hf','','合肥')" href="/city/hf.html">合肥</a>
```

- **CSS selector**: `a.city`（class 为 `city` 或 `city pr0`，`pr0` 是样式修饰）
- **城市 code**: 从 `href="/city/{code}.html"` 提取，或从 `@click="addUsedCity('{code}','','{name}')"` 第 1 个参数
- **城市名**: 标签文本（`<a>…</a>` 内容），或 `addUsedCity` 第 3 个参数
- code 是拼音缩写或全拼混合：`aq`(安庆)、`hf`(合肥)、`bengbu`(蚌埠)、`qz`(泉州)

### 1.3 区县链接结构

```html
<a class="dist" @click="addUsedCity('aq','QS','潜山市')" href="/district/QS.html?city=aq">潜山市</a>
```

- **CSS selector**: `a.dist`（注意：区县块外还有一个 `<span class="dist">` 包裹容器和一个装饰性 `<a>（</a>`）
- **区县 code**: 从 `href="/district/{DISTCODE}.html?city={citycode}"` 提取，大写（`QS`、`FZ`、`LJ`）
- **归属城市**: URL 的 `?city=` 参数，或 `addUsedCity('{citycode}','{distcode}','{name}')` 第 1 个参数
- **区县名**: 标签文本

### 1.4 分组容器层级

```html
<div class="citySel ui0" v-if="type==1">   <!-- 视图1：按拼音首字母分组 -->
  <div class="item" id="selA">
    <div class="tag"><span>A</span></div>   <!-- 字母表头 -->
    <div class="tag2 clearfix">
      <a class="sheng">安徽</a>              <!-- 省份名 -->
      <a class="city pr0" ... href="/city/aq.html">安庆</a>
      <span class="dist"><a>（</a>
        <a class="dist" ... href="/district/QS.html?city=aq">潜山市</a> ...
      </span>
    </div>
  </div>
</div>
<div class="citySel ui1" v-if="type==2"> ... </div>  <!-- 视图2：按省份分组，内容相同 -->
```

### 1.5 提取规则与统计（实测）

- **唯一城市数: 368**，`<a class="sheng">` 省份标签 **31 个**（省/直辖市/自治区）
- **每个城市在 HTML 中出现 2 次**（`type==1` 按字母 + `type==2` 按省份两个视图块），
  **解析器必须按 city code 去重**。
- 区县总链接 322 条；**区县 code 跨城市复用**（如 `TC` 桐城市/天长市… 出现 4 次，`JS` 4 次）——
  **区县不能只用 distCode 做主键，必须用 `(cityCode, distCode)` 联合键**。

**推荐提取正则**（已验证）：

```python
cities = re.findall(r'<a class="city[^"]*"[^>]*href="/city/([^"]+)\.html">([^<]+)</a>', html)
dists  = re.findall(r'<a class="dist"[^>]*href="/district/([^"]+)\.html\?city=([^"]+)">([^<]+)</a>', html)
# cities -> [(code, name)]，需 dict 去重
# dists  -> [(distCode, cityCode, distName)]
```

---

## 2. 城市均价时序页 `https://creprice.cn/urban/qz.html`（泉州）

### 2.1 概况

- 78125 字节，**`<table>` 标签数 = 0**，`<script>` 23 个，`{{ }}` Vue 模板 16 处，"chart" 出现 49 次，
  引入 `echarts.common5.0.0.min.js` + `vue.min.js` + `elementui`。
- 页面 `均价` 关键字只出现在收益率说明文字里，**真实价格数字不在 HTML 内**。

### 2.2 服务端注入的核心配置 `paramsphp`（内联 `<script>`）

这是唯一需要从 HTML 里抓的东西——它给出了调用 API 所需的全部参数：

```javascript
paramsphp = {
    cityCode:'qz', cityName:'泉州',
    distCode:'allsq1',          // 'allsq1' = 全市（非具体区县）
    distName:'', townCode:'', townName:'',
    propType:'11',              // 11 = 住宅
    tradeType:'forsale',        // forsale=二手房挂牌, newha=新房, 其它=租房
    tradeType2:'sale',
    sinceyear:'1',
    iflogin:0,                  // 是否已登录
    source:'eyJ...=',           // base64(JSON)，见下
    pcode:'fujian',             // 省份 code
    ifFuncarea:'',
    lastMonth:'2026-6',         // 最新数据月份
    moniSearchStr:'eyJ...==',   // base64(JSON)
    timeflag:'1783349398',
}
```

`source` 解码后（base64 → JSON）：
```json
{"city":"qz","district":"allsq1","flag":1,"proptype":11,"timeType":"month",
 "sinceyear":1,"town":"","version":"2.0","type":"forsale","ifFuncarea":false,"bldgcode":null}
```

**抓取方式**：`re.search(r"paramsphp\s*=\s*\{.*?\}\s*</script>", html, re.S)` 后逐行取值，
或直接用城市列表页得到的 code（`cityCode` 就是 `/city/{code}` 的 code）拼 API 参数，跳过静态页。

### 2.3 图表容器 DOM（均为空容器，JS 渲染目标）

| id | 含义 |
|---|---|
| `chart_price_cont` / `chart_price_cont_table` | 均价走势（折线）+ 其数据表视图 |
| `chart_price_cont_bar` / `_bar_table` | **价格分布**（柱状）+ 数据表视图 |
| `chart_total_cont*` | 挂牌量/总价走势 |
| `chart_area_cont_bar*` | 面积 |
| `chart_count_cont*` | 套数 |
| `chart_profit_cont_bar*` | 收益率 |
| `chart_qyfb_cont_bar*` | **区域分布（各区县均价）** qyfb=区域分布 |

> `*_table` 容器的表格是 JS 用同一份 JSON 在客户端（`echartsCommon.js` 的 `resetHtml`/`htmltable`）
> 现场生成的，静态 HTML 里是空的。**不要指望抓到这些表格。**

---

## 3. JSON 数据 API（真正的数据源）★核心★

数据加载链路（源码位于 `/js/market/market_index2025.js` + `/js/vue/vueBase.js`）：

```
getApiParams(based, dtype)  → 拼参数对象
  → _addUrlParam(url, params) → 只拼「真值」参数（falsy 的 key 被跳过），? / & 自动处理
  → getApi(url) → jQuery $.ajax({type:'get', dataType:'json'})  → 明文 JSON
```

`getApiParams` 生成的参数（`market_index2025.js` 实测）：

```javascript
{
  city:     cityCode,        // 'qz'
  district: distCode,        // 'allsq1'(全市) 或 'FZ'(区县)
  town:     townCode,        // '' → 被跳过
  proptype: propType,        // 11
  flag:     tradeType=='forsale'?1:(tradeType=='newha'?3:2),
  type:     tradeType,       // 'forsale'
  isv3:     0,               // 0 → 被跳过
  based:    based,           // 'price' / 'total' / 'count' / 'profit' / 'qyfb' ...
  dtype:    dtype,           // 'line' / 'bar'
  sinceyear: 1,              // 仅 price/total/count/profit
  timeType:  'month',        // 'month'/'quarter'/'year'，仅上述几类
  // ifFuncarea:'' → 被跳过
}
```

> `_addUrlParam` 会跳过所有 falsy 值（`if(param[key])`）——所以 `town=''`、`isv3=0`、`ifFuncarea=''`
> 不会出现在 URL 里。`district='allsq1'` 是真值会保留。

> `_getCommonParam`：若 URL 已含 `city=` 则**不再追加** `apiKey`/`userToken`（我们的 URL 都带 `city=`，
> 故无需鉴权参数）。`apiHost` 默认空 → **同源 `https://creprice.cn`**。

### 3.1 均价时序 API `/market/chartsdatanew.html`（based=price&dtype=line）

**实测请求**（泉州全市，月度）：
```
GET https://creprice.cn/market/chartsdatanew.html?city=qz&district=allsq1&proptype=11&flag=1&type=forsale&based=price&dtype=line&sinceyear=1&timeType=month
```

**响应顶层**：
```json
{"data":[…], "code":200, "apiUrl":null,
 "isBuy":0, "isTry":0, "isAllow":1, "isCompare":0, "islogin":0}
```

`data` 是 **3 条 series** 的数组，每条：
```json
{"rows":[…], "tradeCount":"3090", "tradeUnit":"套次",
 "unit":"元/㎡", "chartsName":"供给", "chartsType":"price_line", "flag":"1"}
```

三条 series 的 `chartsName`：
- **series[0] `供给`** — `rows[]`: `{"count":486,"data":16766,"month":"2025-7","value":9373}`
  → **`value` = 该月均价（元/㎡）**，`count` = 挂牌套数，`data` = 另一口径数值
- **series[1] `关注`** — 结构同上（部分月份缺数据）
- **series[2] `价值`** — `rows[]`: `{"count":486,"month":"2025-7","data":9373}`
  → **此 series 的 `data` = 均价**（= series[0] 的 `value`）

> 取「城市月度均价时序」最直接：遍历 **series[0].rows**，取 `{month, value}`（`value`=均价元/㎡，`count`=套数）。
> 实测返回 **13 个月**：`2025-7` … `2026-7`（含最新月）。

### 3.2 价格分布 API `/market/chartsdatanew.html`（based=price&**dtype=bar**）

同一个端点，`dtype` 换成 `bar` 即返回**价格区间分布**：
```
GET .../market/chartsdatanew.html?city=qz&district=allsq1&proptype=11&flag=1&type=forsale&based=price&dtype=bar
```
```json
{"data":[{
   "len":1000, "max":27000, "min":6000, "unit":"元/㎡",
   "chartsType":"price_bar", "chartsName":"供给", "flag":"1",
   "rows":[
     {"data":0.54,"section":"6000-7000","step":"6000"},
     {"data":15.57,"section":"13000-14000","step":"13000"},
     … 共 21 档 …
   ]}]}
```
- `section` = 价格区间（元/㎡），`data` = 落在该区间的**占比（%）**，`step` = 区间下界，`len` = 档宽(1000)
- min/max 为整体价格范围。实测泉州 21 档（6000~27000）。

### 3.3 区县均价 API `/market/distrank2.html`（based=qyfb&dtype=bar）

**这是「各区县均价」的数据源**（页面 `chart_qyfb` 区域分布图）：
```
GET https://creprice.cn/market/distrank2.html?city=qz&district=allsq1&proptype=11&flag=1&type=forsale&based=qyfb&dtype=bar
```
```json
{"showCount":2, "month":"2026-6", "isAllow":true, "rows":[
  {"distCode":"FZ","distName":"丰泽区","cityCode":"qz","cityName":"泉州","cityPinyin":"quanzhou",
   "provinceCode":"fujian","provinceName":"福建",
   "unitPrice":15291, "priceCount":135, "priceLike":-13.94, "priceLink":1.08,
   "lat":24.922012614, "lon":118.617472001, "rankId":1},
  {"distCode":"LJ","distName":"洛江区","unitPrice":10555,"priceCount":34,
   "priceLike":-15.65,"priceLink":-0.13,"rankId":2, …}
]}
```
字段含义：
- **`unitPrice`** = 区县均价（元/㎡），**`distName`/`distCode`** = 区县名/代码
- `priceLike` = 同比涨跌(%)，`priceLink` = 环比涨跌(%)，`priceCount` = 样本套数
- `lat`/`lon` = 经纬度，`rankId` = 排名，`month` = 数据月份

> ⚠️ **付费/匿名限制**：匿名请求 `showCount:2` 只返回 **2 个区县**（泉州实际不止）。完整区县列表可能需要
> 登录/购买。`getapi` 源码里对 `distrank2` 接口**豁免了 `code!=200` 的报错**，说明该接口对匿名做了降级。

---

## 4. 区县均价页 `https://creprice.cn/district/FZ.html?city=qz`（丰泽区）

- 实测 status 200，70434 字节，**`<table>` 数 = 0**，结构与城市页**完全一致**（同样 Vue+ECharts SPA）。
- 其 `paramsphp`：
  ```javascript
  cityCode:'qz', cityName:'泉州', distCode:'FZ', distName:'丰泽区',
  propType:'11', tradeType:'forsale', pcode:'fujian', lastMonth:'2026-6', ...
  ```
- **区县页复用同一批 API**，只是参数 `district=FZ`（而非 `allsq1`）。
  例如区县均价时序：`.../chartsdatanew.html?city=qz&district=FZ&proptype=11&flag=1&type=forsale&based=price&dtype=line&sinceyear=1&timeType=month`

> **结论**：城市页与区县页解析逻辑可复用同一套代码，仅 `district` 参数不同（`allsq1` vs 具体区县 code）。

---

## 5. 解析注意事项 / 特殊值

- **无数据 = JSON 中该 key 直接缺失**（不是 `--`，也不是 `null`）。
  例：均价 series[1] 首行 `{"month":"2025-7"}` 无 `value`/`count`；价格分布某档 `{"section":"6000-7000","step":"6000"}` 无 `data`。
  → 解析器必须用 `.get("value")` / 判断 key 是否存在，缺失时按「无数据」处理。
- **JSON 里的数字是干净的整数/浮点**（`9373`、`16766`、`0.54`），**没有千分位逗号**。
  逗号（`9,373`）只在客户端 `thousandPrice`/`formatPrice` 渲染时才加——走 API 就没有此问题，
  任务里担心的「逗号分隔数字」不存在。
- **编码**：全部 UTF-8，无需 GBK 处理。
- **请求头**：必须带浏览器 `User-Agent`；无 UA 时服务器在 TLS 层断连。无需 Referer/Cookie。
- **付费门控字段**：响应里的 `isBuy`/`isTry`/`isAllow`/`islogin`/`showCount` 反映数据是否被限制；
  匿名下部分数据（尤其区县列表）会被截断，需评估是否需要登录态。
- **缓存/时间戳**：`paramsphp.timeflag`、`lastMonth` 由服务端按最新数据下发；`getapi` 前端有 3 秒本地缓存
  （对爬虫无影响）。

---

## 6. API 端点速查表

| 用途 | 端点 | 关键参数 | 返回要点 |
|---|---|---|---|
| 均价时序（城市/区县） | `/market/chartsdatanew.html` | `based=price&dtype=line` | `data[0].rows[].{month,value,count}` |
| 价格分布 | `/market/chartsdatanew.html` | `based=price&dtype=bar` | `data[0].rows[].{section,data(%),step}` + min/max |
| 各区县均价 | `/market/distrank2.html` | `based=qyfb&dtype=bar` | `rows[].{distCode,distName,unitPrice,priceLike,priceLink,lat,lon}` |
| 挂牌量/套数/收益率 | `/market/chartsdatanew.html` | `based=total/count/profit` | 结构类似 price_line |

**公共参数**：`city={code}` `district={allsq1|区县code}` `proptype=11` `flag=1(二手)/3(新房)/2(租)`
`type=forsale` `sinceyear=1` `timeType=month|quarter|year`

---

## Files Found（本次抓取的原始样本，位于 scratchpad，非仓库内）

| 文件 | 说明 |
|---|---|
| `citySel.html` | 城市列表页原始 HTML（368 城/31 省） |
| `quanzhou.html` | 泉州城市页原始 HTML（含 `paramsphp`） |
| `district_FZ.html` | 丰泽区区县页原始 HTML |
| `api_price_line.json` | 均价时序 API 真实响应 |
| `api_price_bar.json` | 价格分布 API 真实响应 |
| `api_distrank2_qyfb.json` | 区县均价 API 真实响应 |
| `js_market_index2025.js` / `js_vueBase.js` | 数据加载逻辑源码（API 拼参 + ajax 封装） |

> scratchpad 路径：`C:\Users\TaroZero\AppData\Local\Temp\claude\D--CodePack-Urban-Housing-Price-Analysis-System\4fd1bf9b-d8b8-4d8c-8f31-bdc71c35f029\scratchpad\`

## Caveats / Not Found

- **区县完整列表**：匿名 `distrank2` 仅返回 `showCount` 限定的少数区县（泉州仅 2 个），完整数据可能需登录/购买——
  **本次未验证登录态下的返回**。若爬虫需要全部区县均价，需进一步确认鉴权方案（或改用城市列表页拿区县 code +
  逐个请求区县页/区县级 API）。
- 未穷举所有 `based`/`proptype`/`tradeType` 组合的返回差异（仅验证了 price line/bar、qyfb）。
- `total`/`count`/`profit`/`area` 等其它指标的 API 已确认端点相同，但**未逐一抓取样本**。
- 未测试翻页/历史更长时序（`sinceyear` 增大）是否触发付费门控。
