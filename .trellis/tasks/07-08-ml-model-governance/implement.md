# 执行清单：模型版本治理

轻量子任务：改动面小且模式成熟（现有 admin API + Element Plus 表格），
design 并入本清单。

## 顺序步骤

### Step 1 — ModelStore 扩展（train.py）
- [ ] `delete(model_name, version)`：活跃版抛 ValueError；删 pkl+meta
- [ ] `cleanup(keep_last=3)`：按版本序保留最近 N + 活跃版，返回删除清单
- [ ] `best_versions() -> dict[model_name, version]`（MAPE 最低）

### Step 2 — API（predictions.py）
- [ ] `DELETE /admin/predict/models/{model_name}/{version}` → 409/204
- [ ] `POST /admin/predict/models/cleanup?keep_last=3` → 删除清单
- [ ] `ModelVersionOut.is_best`；`list_models` 标注

### Step 3 — 前端（ModelManageView.vue）
- [ ] 删除按钮（活跃禁用 + ElMessageBox 确认）、清理按钮（确认框显示数量）
- [ ] 「最佳」徽标列 + beats_baseline 列（缺省 —）

### Step 4 — 属主修复 + 实操收尾
- [ ] backend 容器 user 或训练写文件 chown（择一落地）
- [ ] 测试：删除/409/清理/最佳标注 单测 + 全量
- [ ] 实操：清理 v1.1~v1.4 等废版本，激活当前最佳版本

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
