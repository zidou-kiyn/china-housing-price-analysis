# NBS 70 城指数导入与月度赋形

## Goal

把国家统计局 70 城月度房价指数（官方、2011~2026、GitHub 直链月更）落库，
并用它替换 ML 年度序列的线性插值——给 70 城的年度价格锚点赋予**真实的
官方月度形状**，这是训练数据真实性的最大单点提升。

## Requirements

- R1 新表 `price_index_snapshot`（迁移 006，按 govstats.md §8.1）：
  region_type/region_id/year_month/dwelling_type(new|second)/base_type(mom)/
  index_value(float)/source，唯一键含全部口径维度。指数禁止塞 PriceSnapshot。
- R2 导入服务：下载 changao1 `merged_housing_data_eng.csv`（70 城×月度×
  新建/二手环比，MIT，GitHub raw 直链），城市名对齐 city 表（英文名→中文名
  crosswalk 静态映射，实施时核实两侧实际名称格式；未匹配城市跳过并报告，
  同 nationwide_import 约定）；幂等 upsert。
- R3 导入入口：`POST /admin/collect/import-index`（admin，异步 job，返回
  导入/跳过统计）；管理页 DataManageView 加导入按钮与统计展示（沿用年度导入
  按钮的模式）。
- R4 ML 月度赋形：`dataset._annual_to_monthly` 支持指数赋形——城市有二手房
  环比指数覆盖区间时，用链式指数还原月度形状并**分段缩放对齐年度锚点**
  （锚点值不变，锚点间形状来自指数而非直线）；无指数城市回退线性插值。
  样本仍标 `is_annual_interp=1`；赋形方式计入 DatasetMeta
  （`shaping: {nbs_index: N 城, linear: M 城}`）。
- R5 训练/预测一致：预测路径经同一构建器获得同样的赋形序列（指数取数
  在构建器内部统一完成，调用方无感知）。
- R6 指数读取服务函数（供 ML 与后续审计任务用）；对外 REST 查询 API 本轮可选。

## Acceptance Criteria

- [ ] 迁移 006 up/down 可跑；重复导入幂等（行数不变）
- [ ] 70 城指数落库（约 2011-01~2026-05，新建+二手环比，约 1.2 万行量级），
      未匹配城市清单在 job 结果可见
- [ ] 北京等指数城市：年度锚点间的月度序列不再是直线（与指数形状相关），
      锚点月值不变；无指数城市行为不变（回退线性）
- [ ] DatasetMeta 可见赋形统计；重训一次，metrics_real_monthly 不劣化
      （或劣化有解释——赋形改变的是插值段，真实月度层理论上不受直接影响）
- [ ] 全量 pytest + 前端 build 通过

## Notes

- hugohe3（含 ADCODE、同比/定基多口径）留作后续扩展，本轮只做 changao1 环比。
- 指数源不进 SOURCE_PRIORITY（不是 price_snapshot 源）；如需展示口径标签，
  另行登记展示元数据。
- 下载走 GitHub raw，当前网络实测可达（研究留档已验证）；实施时若网络抖动，
  下载失败要给出明确 job 错误而非静默空导入。
