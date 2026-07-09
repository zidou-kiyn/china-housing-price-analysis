# M1 creprice 数据采集适配器

## Goal

实现 creprice.cn 数据源的采集适配器。核心发现：价格数据通过 JSON API 获取（非 HTML 表格），仅城市列表页需 HTML 解析。

## Requirements

- BaseSource 抽象基类 + RawRecord dataclass + SourceRegistry 注册机制
- CrepriceSource 实现：
  - 城市/区县列表：解析 `/rank/citySel.html` 的 HTML（唯一需 HTML 解析的页面）
  - 均价时序：调用 `/market/chartsdatanew.html?based=price&dtype=line` JSON API
  - 价格分布：调用 `/market/chartsdatanew.html?based=price&dtype=bar` JSON API
  - 区县均价：对每个区县单独请求区县级 API（规避 distrank2 的匿名限制）
- HTTP 客户端封装：必须带 User-Agent（无 UA 会 TLS 断连）、随机延时 1~3s、重试退避最多 3 次
- 原始数据 JSON 落地：`data/raw/creprice/{city}/{date}.json`
- 单元测试覆盖解析逻辑（用真实 API 响应作为 fixture）

## 技术发现（来自调研）

- creprice.cn 的均价页是 Vue+ECharts SPA，`requests` 抓不到任何价格数据
- 数据全部来自同源 JSON API，明文返回，无加密
- 请求必须带浏览器 User-Agent，不需要 Cookie/Referer/登录
- JSON 数字干净无千分位逗号，缺失数据 = key 不存在（用 `.get()` 处理）
- 城市列表页每个城市出现 2 次（两个视图块），需按 code 去重
- 区县 code 跨城市复用（如 TC 桐城/天长），必须用 (cityCode, distCode) 联合键
- distrank2 API 匿名只返回 showCount 个区县，需改用逐个区县请求规避

## API 端点

| 用途 | 端点 | 关键参数 | 返回 |
|------|------|---------|------|
| 均价时序 | `/market/chartsdatanew.html` | `based=price&dtype=line` | `data[0].rows[].{month,value,count}` |
| 价格分布 | `/market/chartsdatanew.html` | `based=price&dtype=bar` | `data[0].rows[].{section,data(%),step}` |
| 公共参数 | — | `city={code}&district={allsq1|区县code}&proptype=11&flag=1&type=forsale&sinceyear=1&timeType=month` | — |

## Acceptance Criteria

- [ ] `backend/app/collector/base.py` — BaseSource ABC + RawRecord + SourceRegistry
- [ ] `backend/app/collector/sources/creprice.py` — CrepriceSource
- [ ] `backend/app/collector/http_client.py` — UA 轮换 + 延时 + 重试
- [ ] `backend/app/collector/storage.py` — 原始 JSON 落地
- [ ] 城市列表解析返回去重后的 `[{name, code}]`
- [ ] 均价时序 API 解析返回 `[{year_month, supply_price, attention_price, value_price, sample_count}]`
- [ ] 价格分布 API 解析返回 `[{price_range_low, price_range_high, percentage}]`
- [ ] 单元测试用固定 JSON fixture 测试解析逻辑
- [ ] 集成冒烟测试实际抓取一个城市（标记 @pytest.mark.slow）
