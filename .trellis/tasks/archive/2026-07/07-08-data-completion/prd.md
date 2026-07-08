# 训练数据补全与真实性保障（父任务）

## Goal

落实用户三点指令：(1) 逐渐补全 creprice 月度数据；(2) 全国月度数据补全——
Kaggle 调研已定论无现成全国月度数据集，现实方案为 NBS 70 城官方月度指数；
(3) 尽一切可能保证训练数据的有效性与真实性，保证模型有效性。

## 背景（2026-07-08 调研定论）

- creprice：机房 IP 间歇限流非硬封；当前 32 区域、最新 2026-07；无任何定时
  采集机制（无 apscheduler/celery/cron），全靠手动触发。
- Kaggle 无全国城市月度数据集（research/kaggle-datasets.md §0 根本性局限）；
  用户已同意跳过 Kaggle 零散补充。
- NBS 70 城指数：GitHub 免登录直下（绕开 IP 封锁）——
  changao1 `merged_housing_data_eng.csv`（70 城月度环比 2011-01~2026-05，
  GitHub Action 月更，MIT）+ hugohe3 `70cityprice.csv`（含 ADCODE，
  2006~至今，同比/环比/定基多口径）。govstats.md §8.1 已有指数表 schema 建议。
- ML 现状：年度城市序列用线性插值赋月度形状（平滑失真）；指数可提供真实
  月度形状与官方交叉校验锚。

## 子任务地图（执行顺序）

1. `07-08-creprice-scheduler` — creprice 定时采集调度 + 限流退避 + 覆盖轮换扩展
2. `07-08-nbs-index-import` — NBS 指数新表/导入/读 API + 用指数给年度序列赋月度形状
3. `07-08-data-quality-audit` — 导入校验 + 跨源一致性审计 + 重训对比（依赖 2 的指数锚）

## 跨子任务验收标准

- [ ] 定时采集开关/频率可配可见，限流时退避不雪崩；creprice 覆盖城市数可增长
      （受 IP 约束，验收看机制而非一次性数量）
- [ ] NBS 70 城月度指数落库（2011~2026，新/二手×环比），幂等可重跑
- [ ] 70 城中的年度城市，ML 序列改用指数赋形（非线性插值），且训练/预测一致
- [ ] 质量校验能拦截/标记异常值；跨源审计报告可产出（creprice vs 年度 vs 指数
      方向一致性）
- [ ] 数据更新后重训一次，metrics_real_monthly 不劣化（或劣化有解释）
- [ ] 全量后端测试通过（当前基线 303 passed，排除 2 个外网 live 文件）；前端 build 通过

## 约束

- 沿用既有约定：源独立存储、source_policy/SOURCE_META 登记、price_select 读取
  入口、ML meta 只增不改、模型评估引用 metrics_real_monthly。
- 指数是 float 且多口径，禁止塞入 PriceSnapshot（govstats.md §8.1）——新表。
- 定时采集必须尊重限流（退避、批次小、可随时关闭），不得高频轰炸源站。
- 每子任务独立提交。
