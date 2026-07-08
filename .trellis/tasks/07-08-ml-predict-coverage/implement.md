# 执行清单：预测覆盖与置信区间

## 顺序步骤

### Step 1 — 后端预测链路
- [x] `rolling_predict` 返回 data_quality；annual_interp 惩罚系数
- [x] `resid_std_pct` 入 meta（train.py 一行）+ predict 分支（新旧兼容）
- [x] `GET /predict` 接入多源构建器；`PredictionResponse.data_quality`
- [x] prediction 表先删旧版本行后插入（同事务）

### Step 2 — 前端标注
- [x] PredictView.vue：data_quality 标签 + tooltip

### Step 3 — 测试
- [x] 单测：三种 data_quality 判定、惩罚区间、旧 meta 兼容、旧版本行清理
- [x] API 冒烟：年度城市 200（安庆 annual_interp）、北京 mixed、泉州 monthly
- [x] 前端 `npm run build`

## 验证命令

```bash
docker compose exec backend pytest tests/ -x -q
docker compose exec frontend npm run build
docker compose exec postgres psql -U postgres -d housing_price -c "SELECT model_version, count(*) FROM prediction GROUP BY 1;"
```

## 回滚点

- Step 1 各点独立 revert；DELETE 治理可单独去掉不影响其余。

## 审查门

- Step 1 后核对：旧模型（v1.x 无新字段）加载预测全链路不报错。
