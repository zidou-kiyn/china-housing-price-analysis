# Implement — 全国城市年度房价导入（child E）

小步提交。容器内跑测试（勿宿主机 uvicorn/vite）。已验证事实见 prd/design，无需重新调研。

## Step 1 — 下载+解析模块
- [ ] `app/collector/sources/listing_annual.py`：`SOURCES` 常量、`download_csv(source_key, cache_dir=None)`（GitHub raw，缓存 data/listing/，requests 直连不走代理）、`parse_annual_csv(text)`（返回 {province,city,year:int,price:int}，跳过空/异常价）。
- [ ] `tests/collector/test_listing_annual_parse.py`：小 fixture CSV，测解析/过滤/类型。
- commit: `feat(collector): 58/anjuke 全国年度房价 下载+解析`

## Step 2 — 批量导入服务
- [ ] `app/services/nationwide_import.py`：`import_annual(session, source_key)` —— name→city_id 匹配、按城分组、`upsert_price_snapshots(..., source=...)`、统计 matched/skipped/snapshots、清缓存（`del api:cities` + `api:trend:*` 或 invalidate 每城）。
- [ ] 单测：seed 2 个测试城市 + 用小 fixture，断言匹配城落库、未匹配城进 skipped、幂等（跑两次 count 不变）。自清理。
- commit: `feat(service): 全国年度房价批量导入（name→city_id 匹配+溯源）`

## Step 3 — 管理端端点
- [ ] `schemas/admin_job.py`：`AnnualImportRequest`/`AnnualImportResult`。
- [ ] `admin_collect.py`：`POST /admin/collect/import-annual`（同步，require_admin），调用 import_annual，返回统计。
- [ ] `tests/api/test_admin_collect.py`：加导入端点测试（可 monkeypatch download 用小 fixture，避免真下载）。
- commit: `feat(api): 全国年度房价导入端点`

## Step 4 — 实跑 + 前端验证
- [ ] 实跑导入 58：`docker compose exec -T backend uv run python -c "...import_annual(session,'58')..."` 或调端点；确认 ≥320 城落库、打印 skipped 清单。
- [ ] `/cities` 城市数应从 5 增至 ~335；抽查 `GET /prices/trend?region_type=city&region_id=<洛阳id>` 有年度点。
- [ ] Playwright：首页选洛阳/克拉玛依/三亚，走势图渲染（年度点）。
- [ ] （可选）导入 anjuke 补缺。
- commit: `chore(data): 导入 58 全国 ~330 城年度房价 + 验证`

## Step 5 — 前端增强（可选）
- [ ] 数据管理页加"导入全国年度数据"按钮 + 覆盖统计展示。
- [ ] TrendLine/覆盖表标注数据来源与"年度·挂牌"口径（区别于 creprice 月度）。
- commit: `feat(frontend): 全国年度数据导入入口 + 来源标注`

## 验证命令
- 下载核对：`curl -sL "<58 url>" | head`
- name 匹配率（已知 330/365）：见父任务 research/nationwide-datasets.md
- 测试：`docker compose exec -T backend uv run pytest tests/collector/test_listing_annual_parse.py tests/api/test_admin_collect.py -q`
