# M2-5 执行计划

1. [ ] settings 增加 `model_dir`；`.gitignore` 排除 `backend/models/`
2. [ ] `app/ml/features.py`（装配 + 推理行构造）
3. [ ] `tests/ml/test_features.py`（合成数据单元测试，红→绿）
4. [ ] `app/ml/train.py`（自适应窗口训练 + ModelStore 版本化）
5. [ ] `app/ml/predict.py`（滚动预测 + 置信区间）
6. [ ] `tests/ml/test_train_predict.py`（R²/区间/版本断言）
7. [ ] `app/schemas/predict.py` + `app/api/v1/predictions.py`（GET /predict、POST /admin/predict/train）+ router 注册
8. [ ] `tests/api/test_predict.py`（真实库端到端：train → predict → 落库）
9. [ ] 前端 `api/predict.ts`、`PredictChart.vue`、`PredictView.vue`、路由 + RankView 入口
10. [ ] 验证：后端 pytest（单元 + slow）、ruff；前端 type-check/build；浏览器实测 /predict
11. [ ] spec 更新（如有新约定）、提交、finish

## 验证命令

```bash
cd backend && .venv/bin/python -m pytest tests/ml -q && .venv/bin/python -m pytest tests/api -m slow -q && .venv/bin/python -m ruff check app tests
cd frontend && npm run type-check && npm run build
```

## 回滚点

- ml 纯计算层（1~6）与 API 层（7~8）解耦，可分步提交；前端（9）依赖 API 完成。
