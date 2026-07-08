# 训练白名单与模型清理

## Goal

ML 侧落实 creprice-only 方针：训练/预测数据入口加源白名单，删除全部旧模型
与旧预测（多源训练产物，"没有参考意义"），预测功能进入显式空窗期直至
全量爬取完成后重训 v1.8（重训不在本任务内）。

## Requirements

- R1 训练源白名单：`core/source_policy.py` 加 `TRAINING_SOURCES = ("creprice",)`；
  训练与预测的数据装载入口（`app/ml/dataset.py::build_multi_source_series` 的
  上游取数处）按白名单过滤 rows_by_source，非白名单源的行进不了训练/预测集。
  年度校准（ratio_curve）、指数赋形、插值降权等多源代码路径保留但自然走不到
  （不 revert，可逆）。
- R2 模型清理：删除 `backend/models/` 下全部模型版本（random_forest v1.x、
  xgboost 全部）与活跃指针 `active.json`；顺带删除遗留快照目录
  `backend/models.bak-governance/`（已 gitignore 的本地目录）。优先走既有
  模型治理 API/UI 删除，走不通再手工清目录。
- R3 预测数据清理：清空 `prediction` 表全部旧预测行（均为多源模型产物，
  含 330 年度城市 data_quality=annual_interp 的插值预测）。
- R4 空窗兜底：无活跃模型时——
  a) `PredictView.vue` 显式"数据积累中，暂无可用模型"空态，不报错；
  b) 预测相关 API 返回明确的"无活跃模型"响应（4xx + 语义化 detail 或空态
     结构，与前端约定一致）；
  c) 数据质量报告（admin/data-quality/report）"模型新鲜度"一节在无活跃模型时
     优雅降级（提示待重训，而非异常）。
- R5 重训触发条件留档：v1.8 重训的前置 = 07-07-full-data-crawl 全量首采完成
  （数百城覆盖统计回填该任务 notes）。届时新开任务执行：白名单生效下重训、
  按模型治理流程激活。本任务只留档不执行。

## Acceptance Criteria

- [ ] 白名单生效：构造含 58/kaggle 行的取数场景，训练集只含 creprice 行
      （单测覆盖）
- [ ] `backend/models/` 无模型文件、无 active.json；`prediction` 表 0 行
- [ ] 预测页显式空窗提示；预测 API 无活跃模型时按约定响应，不 500
- [ ] 质量报告无活跃模型时正常产出（新鲜度一节降级提示）
- [ ] 全量 pytest 通过（涉及活跃模型假定的既有测试相应调整）+ 前端 build 通过

## Notes

- 与 07-08-source-scoped-views 互相独立，可并行。
- 训练数据质量防线：导入校验器（snapshot_validator，07-08-data-quality-audit
  已落地）继续拦截 creprice 入库异常值。
- ml-pipeline 相关约定见 `.trellis/spec/backend/database-guidelines.md`
  §ML training-data path，实施时同步更新该节。
