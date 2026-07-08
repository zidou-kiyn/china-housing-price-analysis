# 设计：creprice 定时采集调度

## 模块

新增 `backend/app/services/collect_scheduler.py`：

```
CollectScheduler（asyncio 后台任务，FastAPI lifespan 启动/停止）
  loop: 每 60s 醒来 → 读 settings KV → enabled 且到达触发时刻且今日未跑
        → _pick_targets() → job_runner.submit("collect", ...) 复用
          admin_collect._run_collect 的任务体（抽出可复用函数）
```

不引入 APScheduler/celery：单进程 asyncio 循环足够，且配置即时生效
（每次醒来重读 KV）。多副本部署需分布式锁——本轮单副本假定，代码留注。

## 配置（admin settings KV，沿用既有 admin_settings 机制）

| key | 默认 | 说明 |
|---|---|---|
| collect_schedule_enabled | "false" | 总开关 |
| collect_schedule_time | "03:30" | 每日触发时刻（容器本地时区） |
| collect_schedule_batch | "5" | 每批城市数 |
| collect_schedule_state | JSON | last_run_date/last_run_at/last_result 摘要（调度器写） |

## 目标选择 `_pick_targets(db, batch)`

1. 续采：有 creprice 快照但 `max(year_month) < 当前月` 的城市，按 max(year_month)
   升序（最旧优先）。
2. 扩展：无 creprice 快照的城市，按 city.id 升序，接在续采后补足 batch。
   轮换游标：KV 存 last_expand_city_id，下批从其后继续，扫完回绕。

## 限流保护

- 城市间 `asyncio.sleep(uniform(10, 20))`（常量 SCHEDULE_INTER_CITY_DELAY）。
- 熔断：批内连续 3 城采集失败（runner 返回 ok=false 或抛错）→ 终止本批，
  state 记 circuit_broken=true 与已完成/跳过清单。
- 不叠加新的请求级重试（http_client/runner 既有策略不动）。

## 复用与接线

- `admin_collect._run_collect` 现为手动采集任务体：抽出为可复用（调度器与
  手动路径共用），保持 job 结果结构一致 → 管理页任务列表天然可见定时批次。
- job payload 增 `"trigger": "schedule"` 标记以便区分（列表展示可选）。
- lifespan：`app/main.py` 启动时 `scheduler.start()`，关闭时 cancel；测试环境
  （pytest）默认不启动（读环境变量或 settings 判定），避免测试悬挂任务。

## 前端（DataManageView）

「定时采集」卡：el-switch（开关）+ el-time-select（时刻）+ el-input-number
（批次）+ 上次运行摘要（时间/成功数/熔断标记）。读写走既有
GET/PUT /admin/settings。

## 权衡

- 每日一批而非小时级：月度数据源，天级足够；限流环境下更频繁只会更快触发封锁。
- 熔断按「连续失败」而非总失败率：限流表现为连续 SSL EOF/502，连续 3 次即
  强信号；散发失败（个别城市无数据）不应中断扩展。
