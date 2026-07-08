# 执行清单：creprice 定时采集调度

## 顺序步骤

### Step 1 — 任务体复用与调度器
- [ ] `admin_collect._run_collect` 抽出为调度器可复用形态（保持 job 结果结构）
- [ ] `services/collect_scheduler.py`：60s 循环、KV 读取、当日去重、时刻判定
- [ ] `_pick_targets`：续采（缺当月，最旧优先）+ 扩展（无数据，游标轮换）
- [ ] 城市间随机 sleep + 连续 3 失败熔断 + state 摘要写 KV
- [ ] lifespan 接线（pytest 环境不启动）

### Step 2 — 配置面
- [ ] settings KV 四个键 + schema/校验（时刻格式、批次 1~20）
- [ ] DataManageView「定时采集」卡（开关/时刻/批次/上次运行摘要）

### Step 3 — 测试与验证
- [ ] 单测：目标选择两类排序、熔断、当日去重、配置即时生效（mock 时钟/KV）
- [ ] 容器内实测：时刻设近未来 → job 自动出现并执行（可用 1 城小批）
- [ ] 全量 pytest + ruff + 前端 build

## 验证命令

```bash
docker compose exec -T backend uv run pytest tests/ -x -q \
  --ignore=tests/pipeline/test_runner_live.py --ignore=tests/collector/test_creprice_live.py
backend/.venv/bin/ruff check app tests scripts   # 宿主
docker compose exec -T frontend npm run build
```

## 回滚点

- 调度器为独立文件+lifespan 两行，可整体摘除；KV 键无迁移。

## 审查门

- Step 1 后自查：调度器异常不得拖垮应用启动/关闭；循环内全部异常捕获并记 state。
