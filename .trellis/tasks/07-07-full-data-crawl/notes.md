# 全量爬取执行记录

## 执行状态（随批次更新）

| 时间 | 动作 | 结果 |
|------|------|------|
| 07-07 23:35 | 刷新城市列表（admin-data-collect 验证时） | 368 城入库，省份齐全 |
| 07-07 23:45 | adcode 全国索引回填（首次爬图触发） | 363/368 回填，5 城名称歧义待显式指定 |
| 07-08 00:0x | 莆田(pt)数据+图、三明(sm)/龙岩(ly)图 | 成功（功能验证时顺带完成） |
| 07-08 00:2x | creprice 触发 IP 级限流（SSL EOF） | **数据采集暂停等冷却**，Monitor 每 5 分钟探测 |
| 07-08 00:2x | 地图全量爬取任务 #97（362 城，DataV 独立源不受影响） | success：323 成功 / 39 失败 |
| 07-08 00:4x | 4 个自治州显式 adcode 补爬（hnz/bazhou/bozhouxj/kz） | 全部成功，**地图覆盖 333/368** |
| 07-08 00:3x | creprice 恢复探测 200，首批 20 城采集任务 #98 提交 | 进行中（含 bj/cq 大城市） |

## 执行手册（后续会话续跑用）

1. **源站探测**：`docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('https://www.creprice.cn/rank/citySel.html', headers={'User-Agent':'Mozilla/5.0'}), timeout=10).status)"` — 200 才继续。
2. **分批采集**（管理端 API，admin/admin123456 登录取 token）：
   - 取缺数据城市：`GET /api/v1/admin/collect/cities?page_size=500` 筛 `latest_month == null`
   - 每批 20–50 城 `POST /api/v1/admin/collect {"city_codes": [...]}`（严格串行限速，禁止调低延时）
   - 轮询 `GET /api/v1/admin/jobs/{id}`，每批完成后记录 result 中失败城市到本文件
   - 每城约 45s–3min（区县数决定），全量预估 6–15 小时，分多次执行；采集幂等可中断重跑
3. **失败重试**：失败城市重试一轮；creprice 无数据的小城市属正常，标注即可。
4. **补图**：数据批次全部完成后 `POST /admin/geo/fetch {"all_missing": true}` 兜底（有区县但缺图）。
5. **验收**（见 prd.md）：≥95% 城市有区县+最新快照；抽查北上广蓉汉 5 城前端展示；预测可用；覆盖统计写回本文件。

## 失败清单

### 地图（终态：35 城无图，均为数据源天然限制，不再重试）

不设区城市（DataV 无 `_full` 区县边界，前端地图无区县可着色，属正常）：
- 广东：dg(东莞) zhongshan(中山)；甘肃：jyg(嘉峪关)；河南：jiyuan(济源)
- 湖北省直辖：qianjiang(潜江) snj(神农架) tm(天门) xiantao(仙桃)
- 海南省直辖县市（15）：baisha baoting changjiang cm danzhou da df ledong lg lingshui qh qiongzhong tunchang wanning wc wzs
- 新疆兵团市（12）：ale beitun hyh kkdl ky shz shuanghe tmg tmsk wjq xinxing(无 adcode)
- 已补爬成功：hnz=632500 bazhou=652800 bozhouxj=652700 kz=653000（自治州缩写名索引未命中，显式指定后成功）

### 数据采集

（待各批次执行后填写）

## 已知问题

- adcode 缺失 5 城：任务 result 中会以 "无 adcode" 失败呈现，需人工 `scripts/fetch_geo.py <code>=<adcode>` 显式指定。
- 直辖市（北京/上海等）在 creprice 的区县为「区」级，正常采集；数据源部分小城市无区县级数据属天然限制。

## 2026-07-08 暂停记录（用户指令）

- 采集批次 1（#98）在 3/20 时经重启 backend 终止（interrupted by restart），已采 3 城数据有效（幂等 upsert）。
- 暂停原因：直连触发过限流，改为先落地「采集代理设置」功能（07-08-proxy-settings，已完成）。
- **恢复条件**：用户在 数据管理页 → 采集代理 卡片配置 iproyal 国内 IP 代理（境外代理已实测被 creprice 拒绝）、测试连通后启用，再按本手册「分批采集」继续。resin 代理 URL 已存库（未启用）。
