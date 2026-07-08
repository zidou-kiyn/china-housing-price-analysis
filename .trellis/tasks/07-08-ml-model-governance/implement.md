# 执行清单：模型版本治理

轻量子任务：改动面小且模式成熟（现有 admin API + Element Plus 表格），
design 并入本清单。

## 顺序步骤

### Step 1 — ModelStore 扩展（train.py）
- [x] `delete(model_name, version)`：活跃版抛 ValueError；删 pkl+meta
- [x] `cleanup(keep_last=3)`：按版本序保留最近 N + 活跃版，返回删除清单
- [x] `best_versions() -> dict[model_name, version]`（MAPE 最低）

### Step 2 — API（predictions.py）
- [x] `DELETE /admin/predict/models/{model_name}/{version}` → 409/204
- [x] `POST /admin/predict/models/cleanup?keep_last=3` → 删除清单
- [x] `ModelVersionOut.is_best`；`list_models` 标注

### Step 3 — 前端（ModelManageView.vue）
- [x] 删除按钮（活跃禁用 + ElMessageBox 确认）、清理按钮（确认框显示数量）
- [x] 「最佳」徽标列 + beats_baseline 列（缺省 —）

### Step 4 — 属主修复 + 实操收尾
- [x] backend 容器 user 或训练写文件 chown（择一落地）
      —— 决策：选 chown 方案。`ModelStore._align_owner` 在 save/set_active 写完后把
      文件属主对齐 base_dir（宿主挂载目录）属主并 chmod 664/775；非 root 运行时为
      空操作。不改 compose user：dev 容器依赖 root 做 `uv run` 首次依赖同步到匿名卷
      `/app/.venv`，非 root 会破坏启动流程。
- [x] 测试：删除/409/清理/最佳标注 单测 + 全量（301 passed，基线 284 + 新增 17）
- [x] 实操：经 API 全库重训 RF 一次（新 meta 含 dataset/ratio_curve/resid_std_pct，
      解决活跃模型为旧 meta 的遗留），清理 v1.1~v1.4 等废版本，激活当前最佳版本
      —— job #402 训出 v1.7（31232 样本，MAPE 0.25 / real_monthly 2.71，
      beats_baseline=true）；cleanup keep_last=3 删 rf v1.0~v1.4；active → v1.7；
      备份留于 backend/models.bak-governance（回滚点）；容器内一次性 chown 已把
      存量 root 属主文件（v1.5/v1.6/xgb v1.1）对齐宿主用户
- [x] 实操：一次性 SQL 清理 prediction 表存量旧版本行（region 44/109/236 等
      未被重新预测过的 v1.0/v1.1 残留）
      —— DELETE 24 行（v1.0×6 / v1.1×3 / v1.5×15），表内仅剩活跃 v1.7 行；
      验证：安庆（仅年度源城市 380）预测 200，data_quality=annual_interp

## 验证命令

```bash
docker compose exec backend pytest tests/ -x -q
docker compose exec frontend npm run build
ls -la backend/models/random_forest/  # 属主与清理结果
cat backend/models/active.json
```

## 回滚点

- Step 1~3 增量 API/UI，逐个 revert 安全；Step 4 实操前先 `cp -r backend/models` 备份。

## 审查门

- Step 4 清理属破坏性操作：执行前列出将删文件清单自查（活跃/最佳必须不在内）。
