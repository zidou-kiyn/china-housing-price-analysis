# ML 管理：模型版本治理

## Goal

模型版本可删除、可清理，最佳版本一目了然，激活流程不再滞后
（现状：v1.5 活跃而更优的 v1.6 未激活，v1.1~v1.5 实验版本堆积）。

## Requirements

- R1 删除 API：`DELETE /admin/predict/models/{model_name}/{version}`；活跃版本
  拒绝删除（409）；删 pkl + meta 两个文件。
- R2 批量清理 API：`POST /admin/predict/models/cleanup`，保留每模型最近 N 版
  （默认 3）+ 活跃版本，返回删除清单。
- R3 最佳版本提示：模型列表标注 `is_best`（同模型下 MAPE 最低的版本）；
  前端「最佳」徽标；列表默认按 model_name + 版本排序不变。
- R4 前端 ModelManageView：行内删除按钮（活跃版禁用，二次确认）、
  「清理旧版本」按钮（展示将删数量确认）、最佳徽标、基线对比列
  （beats_baseline，来自 ml-train-eval，缺省显示 —）。
- R5 版本文件属主：容器内训练写出的文件归 root 导致宿主侧管理不便——
  backend 容器改用非 root 用户运行或写文件后 chown（择一，实施时定）。

## Acceptance Criteria

- [ ] 删除非活跃版本成功且文件消失；删除活跃版本返回 409
- [ ] cleanup 后每模型剩 ≤N+1 个版本（含活跃），active.json 指针仍有效
- [ ] 管理页可见最佳徽标/删除/清理交互；活跃版删除按钮禁用
- [ ] 全量测试通过 + 前端 build 通过
- [ ] 本轮遗留实验版本（rf v1.1~v1.4 等非最佳非活跃）实际清掉，active 指向
      当前最佳版本（操作演示即验收）

## Notes

- 完全独立子任务，不依赖其它三个。
- ModelStore 已有 versions/load/save，删除是自然补全；不引入模型注册表 DB 化
  （文件方案当前规模足够）。
