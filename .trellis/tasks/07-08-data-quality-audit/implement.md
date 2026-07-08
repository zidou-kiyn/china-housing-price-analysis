# 执行清单：数据质量校验框架

轻量任务，design 并入本清单。

## 顺序步骤

### Step 1 — 导入校验器
- [x] `app/pipeline/snapshot_validator.py`：值域/跳变/格式校验，返回
      (accepted, rejected, flagged) 结构；常量集中定义
- [x] 接入三条写入路径：pipeline loaders（creprice）、nationwide_import（年度）、
      index_import 的价格快照如适用（指数表不适用值域规则，只做格式）
- [x] job 结果透出 rejected/flagged 计数

### Step 2 — 审计报告
- [x] `app/services/data_quality.py`：四节报告（重叠比值离群、creprice vs 指数
      方向一致率、年度 vs 指数同比一致率、覆盖新鲜度）+ 模型新鲜度对比
      （库指纹 vs 活跃模型 meta.dataset.fingerprint）
- [x] `GET /admin/data-quality/report` + schema
- [x] 前端质量入口卡（要点：离群数/一致率/新鲜度徽标）
- [x] 附带小修：`ModelStore.best_versions` 改为 metrics_real_monthly.mape 优先
      （缺失回退 metrics.mape）；is_best/前端「最佳」徽标语义不变

### Step 3 — 测试与实操
- [x] 单测：校验器边界值、方向一致率计算（构造已知答案）、无指数数据降级、
      新鲜度判定、best_versions 新口径
- [x] 实操：真实库跑报告，结论写入本文件留档（见下）
- [x] 全量 pytest + ruff + 前端 build（380 passed，基线 345 + 新增 35）

## 验证命令

```bash
docker compose exec -T backend uv run pytest tests/ -x -q \
  --ignore=tests/pipeline/test_runner_live.py --ignore=tests/collector/test_creprice_live.py
curl -s -H "Authorization: Bearer <admin>" localhost:8000/api/v1/admin/data-quality/report | jq .
```

## 回滚点

- 校验器可按路径逐个摘除；报告为只读端点，无状态。

## 审查门

- Step 1 后自查：校验器不得改变既有合法数据的导入行为（回归：年度重导入幂等
  行数不变）——已实测：58 年度真实重导入 3206 行 → 3206 行，matched 330、
  rejected 0、flagged 0，幂等行为与校验前完全一致。

## 实现决策（偏离/裁量）

- 报告**不加缓存**：即时计算实测仅 ~0.8s（全库 3,769 快照 + 12,950 指数行 +
  指纹重算），且「重训后新鲜度徽标立刻翻转」是验收语义，TTL 缓存会给出
  误导结论。
- 跳变检测只在**写入批次内部**比较相邻自然月（不查库）；年度点相隔 12 月
  天然不触发环比规则，跨批次/跨源异常由审计报告兜底。
- index_import 不接 snapshot_validator：不写 price_snapshot，值域规则不适用；
  格式与区间校验（年/月合法、指数 50~200）已在 parse_index_csv 内自带，
  docstring 已注明该约定。
- 方向一致率的"平"（|Δ|<0.1%）不计入分母：指数横盘期大量报 100.0，计入会
  稀释判别力；note 字段随报告透出该口径。
- **模型版本清理**：best_versions 改口径后，多源构建器之前的旧版本
  random_forest v1.5（headline 4.75）/ v1.6（泉州单城，headline 1.95）会以
  不可比的小范围 headline 抢走「最佳」徽标——已移入
  `backend/models.bak-pre-builder/`（git 忽略、可逆），修后 best=v1.8 符合预期。
  xgboost v1.0/v1.1 均无 real_monthly 指标，best=v1.0 维持原判，未动。

## 实操留档：真实库审计结论（2026-07-08）

报告耗时 0.77s，四节齐全：

1. **多源重叠比值**：重叠对 8、离群 0、比值中位数 0.987。8 对全部是北京
   kaggle_lianjia（成交）× listing_annual_58（挂牌）的 12 月重叠
   （2010~2017），比值 0.79~1.12，均在 [0.5, 2.0] 域内——与 ratio_curve
   逐年校准的实证漂移一致。creprice 仅保留近约 12 个月窗口，与 58 年度
   （最新 2024-12）无月份交集，故无 creprice×年度重叠对。
2. **creprice 环比 vs NBS 二手指数环比**：重叠 4 城（厦门、安庆、泉州、
   福州）、40 对（7 对含平剔除）、比较 33 对、一致 23 → **一致率 69.7%**。
   方向多数一致；不一致的对集中在 |环比| < 1% 的小幅波动月（挂牌均价与
   成交指数的口径差），无系统性反向，暂无需处理。
3. **58 年度同比 vs 指数 12 月链乘同比**：70 城全部覆盖、813 对（27 对含平
   剔除、0 对因指数缺月跳过）、比较 786 对、一致 600 → **一致率 76.3%**。
   2011~2024 年跨度下 3/4 同向，年度挂牌数据与官方指数总体方向可信；
   不一致集中在涨跌拐点年（挂牌滞后于成交指数转向），属口径特性而非脏数据。
4. **覆盖/新鲜度**：creprice 40 区域、最新 2026-07（距今 0 月）；
   kaggle_lianjia 1 城、最新 2018-01（距今 102 月，历史静态集，符合预期）；
   listing_annual_58 330 城、最新 2024-12（距今 19 月，年度源年更节奏正常）；
   nbs_github_changao1 指数 70 城 12,950 行、最新 2026-05（距今 2 月，
   源仓库月更节奏正常）。
5. **模型新鲜度**：活跃 random_forest v1.8 指纹 70d19157d3ef3cfa ==
   当前库重算指纹 → **fresh**，无需重训（v1.8 即今日指数赋形后所训）。
   stale 路径已用 v1.7 元数据实测验证（86c302009e90fe47 ≠ 当前库 → stale）。

**离群/异常清单**：无比值离群；无指数缺月跳过；导入校验重跑 58 年度
rejected=0。**建议**：kaggle_lianjia 距今 102 月为静态历史集属预期，无需
处理；后续新源接入时沿用 snapshot_validator + 本报告即可发现口径漂移。

**best_versions 修正后**：random_forest best v1.8（real 2.70 < v1.7 real
2.71，headline 虚低 0.25/0.31 不再作数）、xgboost best v1.0；active=v1.8
同时持有「最佳」徽标。
