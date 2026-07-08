# 执行清单：creprice 定时采集调度

## 顺序步骤

### Step 1 — 任务体复用与调度器
- [x] `admin_collect._run_collect` 抽出为调度器可复用形态（保持 job 结果结构）
      → 共用循环落在 `services/collect_tasks.py::run_collect`，手动路径行为不变
- [x] `services/collect_scheduler.py`：60s 循环、KV 读取、当日去重、时刻判定
      → 当日去重用 KV 原子抢占（ON CONFLICT DO UPDATE WHERE last_run_date IS
      DISTINCT FROM today），兼容 prod uvicorn --workers 2 的双循环
- [x] `_pick_targets`：续采（缺当月，最旧优先）+ 扩展（无数据，游标轮换）
- [x] 城市间随机 sleep + 连续 3 失败熔断 + state 摘要写 KV
      （仅定时路径带节流/熔断；游标只越过实际尝试的扩展城市）
- [x] lifespan 接线（pytest 环境不启动：`main._scheduler_enabled` 判
      `"pytest" in sys.modules`，另留 COLLECT_SCHEDULER_DISABLED=1 环境变量）

### Step 2 — 配置面
- [x] settings KV + schema/校验（时刻格式、批次 1~20）
      → 偏离说明：设计原列 4 个标量键；AppSetting.value 为 JSON dict，收敛为
      2 个 dict 键——`collect_schedule`（配置，管理端整体覆盖）与
      `collect_schedule_state`（状态，仅调度器写），避免读改写竞争
- [x] DataManageView「定时采集」卡（开关/时刻/批次/上次运行摘要 + 熔断标记；
      时刻按容器本地时区，实测容器为 UTC，卡片提示已注明）

### Step 3 — 测试与验证
- [x] 单测：目标选择两类排序+游标回绕、熔断+连败归零、当日去重、时刻判定、
      配置即时生效、409 让位撤销抢占、API 校验（tests/services/
      test_collect_scheduler.py 21 例 + tests/api/test_admin_settings.py +7 例）
- [x] 容器内实测：07:36 UTC 设近未来时刻+批次 1 → 07:36:59 自动出现
      job #443（payload.trigger=schedule），采集 aq（安庆，扩展目标）成功
      85 快照/166 分布，state 写入 last_run/摘要/expand_cursor=380；
      实测后开关已复位为关闭（默认配置）
- [x] 全量 pytest（330 passed，基线 303 + 新增 27）+ ruff 通过 + 前端 build 通过

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
  → 已核：`_loop` 捕获一切非 Cancelled 异常并 best-effort 写 state.last_error；
  `stop()` 未启动时为 no-op；提交失败/409 撤销当日抢占，60s 后自动重试。
