# 执行清单：数据质量校验框架

轻量任务，design 并入本清单。

## 顺序步骤

### Step 1 — 导入校验器
- [ ] `app/pipeline/snapshot_validator.py`：值域/跳变/格式校验，返回
      (accepted, rejected, flagged) 结构；常量集中定义
- [ ] 接入三条写入路径：pipeline loaders（creprice）、nationwide_import（年度）、
      index_import 的价格快照如适用（指数表不适用值域规则，只做格式）
- [ ] job 结果透出 rejected/flagged 计数

### Step 2 — 审计报告
- [ ] `app/services/data_quality.py`：四节报告（重叠比值离群、creprice vs 指数
      方向一致率、年度 vs 指数同比一致率、覆盖新鲜度）+ 模型新鲜度对比
      （库指纹 vs 活跃模型 meta.dataset.fingerprint）
- [ ] `GET /admin/data-quality/report` + schema
- [ ] 前端质量入口卡（要点：离群数/一致率/新鲜度徽标）

### Step 3 — 测试与实操
- [ ] 单测：校验器边界值、方向一致率计算（构造已知答案）、无指数数据降级、
      新鲜度判定
- [ ] 实操：真实库跑报告，结论写入本文件留档
- [ ] 全量 pytest + ruff + 前端 build

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
  行数不变）。
