# Journal - zidou-kiyn (Part 1)

> AI development session journal
> Started: 2026-07-06

---


## 2026-07-07 · 07-07-compose-unify 完成

- compose 收敛为基准（生产安全）+ override（dev 差异），DB/Redis/backend 全形态不暴露宿主机端口，卷统一 `./data/`；dev 全容器化，脚本/pytest 改 `docker compose exec backend` 执行。
- 踩坑记录：① override 对 `ports`/`env_file` 是合并语义，需 `!override` 标签（Compose ≥2.24.4）；② dev 源码挂载会遮蔽镜像 `.venv`，用匿名卷 `/app/.venv` 保护；③ dev/prod 共享 frontend 镜像 tag 会互相覆盖（nginx 镜像跑 npm 崩溃），已显式区分 `housing-price-frontend:dev|prod`；④ `vue-tsc --build` 因 tsconfig.node 缺 `noEmit` 会发射 `vite.config.js`（Vite 加载优先级高于 .ts），这是当初遗留文件的根因，已修。
- 遗留问题（不属本任务）：`npm run lint` 是脚手架死脚本，eslint 从未进依赖；宿主机曾遗留旧会话 vite/uvicorn 进程占端口，已清理。
- 验收全过：pytest 159 passed（容器内）、E2E 6 passed、prod 8080 与 dev 5173 双形态验证。

## 2026-07-07 · 07-07-admin-user-mgmt 完成

- 后端：/admin/users 增加 keyword/role/is_active 筛选；新增 status 切换与硬删除端点，自我操作返回 400；12 个 pytest 用例。
- 前端：UserManageView 加筛选栏与封禁/启用/删除操作列，自己行禁用；Playwright MCP 浏览器实测全流程通过（el-button 用原生 click 绕合成事件坑，见 memory）。
- 全量回归：pytest 171 passed，E2E 6 passed。

## 2026-07-08 · 07-07-admin-data-collect 完成

- 交付：admin_job 表 + job_runner（asyncio 后台执行、kind 互斥部分唯一索引、启动清理）；采集/覆盖查询/任务查询 API；GeoJSON 服务化（DataV 下载、adcode 全国索引回填 363/368、data/geo 落盘、/api/v1/geo/{code}）；前端数据管理页（多选/筛选/轮询进度/历史）。
- 数据副产品：全国 368 城已入 city 表（带省份）；莆田完整采集；三明/龙岩地图已爬。
- 关键决策：公开 /cities 改为仅返回有区县数据的城市，避免 368 个空城市污染用户端选择器（采集完成自动失效 api:cities 缓存，新城市即时出现）。
- 坑：ORM identity map——任务体内 backfill 后重读同 session 需经 ORM 更新对象而非 Core update（测试打桩踩到）；data/ 目录容器 root 属主，宿主机写入要走 docker compose cp / exec。
- 验证：后端 201→235 tests；E2E 9 用例；dev 与 prod 双形态真实闭环（prod workers=2 下任务正常）。

## 2026-07-08 · 07-07-admin-model-mgmt 完成

- 后端：POST /admin/predict/train 改真后台任务（asyncio.to_thread 包 train_model），TrainRequest 迁 city_codes 列表，训练互斥 409，新版本不自动激活；测试改任务轮询式 + 互斥/失败用例（12 passed）。
- 前端：ModelManageView（版本表/训练表单/进行中轮询/切换活跃二次确认），抽 usePolling composable 并回改 DataManageView；E2E 12 用例全过。
- 实测：全量数据训练 v1.1/v1.2 产出，切 v1.1 后 /predict 即时用新模型（莆田新城市可预测），切回 v1.0。
- 注意：tests/pipeline/test_runner_live.py（真实访问 creprice）当日多次真实采集后被源站 SSL 层限流而失败（外部因素，其余 199 项全过）——full-data-crawl 执行时须严格限速、避免高频重试。

## 2026-07-08 · 07-08-proxy-settings 完成（full-data-crawl 暂停）

- 用户指令终止全量采集（批次 1 于 3/20 重启终止），新增管理端采集代理设置功能。
- 交付：app_setting KV 表（003 迁移）+ GET/PUT/test 代理端点（密码脱敏、URL 缺省=仅改开关）+ CrawlerHttpClient 构造时自动读设置（geo/DataV 保持直连）+ 数据管理页代理卡片。
- 实测结论：用户自建 resin 代理（美国出口）本身可用但 creprice 拒境外 IP（TLS 断连）→ 已存库未启用；采集恢复需用户自配 iproyal 国内代理（密钥用户自持）。
- 教训：测试 fixture 若清理与真实配置同 key 的数据,必须暂存恢复而非直接删除（第一版 teardown 清掉了刚保存的真实配置）。

## 2026-07-08 · 07-08-creprice-first 完成（源隔离展示 + 训练白名单清理）

- **源隔离展示（07-08-source-scoped-views）**：读取层从跨源合并改单源直读——删 `select_merged_snapshots`/`priority_case`，价格/分析端点加 `source` 查询参数（缺省 creprice，非登记源 422），新增 `select_snapshots_for_source`；新增 `GET /prices/index/trend`（NBS 指数独立路径）。前端建全局 source store（Pinia+localStorage）、顶栏切换器、五视图按源重拉、NBS 指数曲线（IndexTrendLine）、rank/compare/map/dashboard「指数源不适用」、预测入口仅 creprice 可见。
- **训练白名单清理（07-08-training-whitelist-cleanup）**：`TRAINING_SOURCES=("creprice",)` + `training_rows_only` 加在**装载入口**（非构建器纯函数，故 test_dataset 多源单测零改动、保留路径可逆）；预测 API 无活跃模型改 `NO_ACTIVE_MODEL`，PredictView 显式空窗态；质量报告 `model_freshness` 无模型降级 unknown。
- **破坏性清理**（本地状态、gitignore、不可逆，父任务 grilling 锁定授权）：清空 prediction 表（6→0）、删 `backend/models/` 全部模型 + active.json + 遗留 `models.bak-governance/`；空窗期至 full-data-crawl 完成后重训 v1.8。
- **覆盖塌缩（有意为之）**：年度城市不再可预测（无 creprice→404）、混合城市仅 monthly；据此改写 2 个既有预测覆盖测试。
- 验证：后端 397 passed（live 网络测试 deselect，缺国内 IP 既有失败）、前端 build、浏览器实测（泉州 creprice 仅 2025-07 起 vs 58 年度 2011-2024、切换器刷新持久化、NBS 指数曲线、预测入口按源显隐、空窗 404+NO_ACTIVE_MODEL、报告 unknown 降级）。
