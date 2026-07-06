# 城市房价分析系统 - 项目开发规划与架构设计

## Goal

基于 .source 需求文档进行整体规划：需求梳理(PRD)、爬虫站点调研(playwright)、四层架构设计(含架构图)、技术选型(FastAPI+Vue3+ECharts, 混合数据源策略)、分阶段开发计划，产出可指导稳定开发的完整文档到 docs/

## Requirements

- 从 `.source/` 需求文档提炼功能需求、非功能需求与用户角色
- Playwright 实测数据源反爬（链家/安居客/creprice），确定混合数据源策略
- 敲定技术栈（FastAPI + Vue3 + ECharts + PostgreSQL + Redis）
- 设计四层架构（采集→数据→分析预测→应用）
- 产出 `docs/` 完整开发文档集（9 份规格文档 + 1 份导航 README）
- 跨文档术语/表名/字段/API 路径一致性校验
- 规划三阶段开发里程碑（M1 基础 / M2 增强 / M3 完善）

## Acceptance Criteria

- [x] `.source/` 需求文档已分析，功能需求提炼为 docs/01
- [x] Playwright 数据源实测完成，调研报告见 research/crawler-source-survey.md
- [x] 关键技术方向已敲定（见 design.md §5 权衡表）
- [x] Trellis 三件套（prd/design/implement）齐备
- [x] docs/ 全部 10 份文档产出（README + 01~09）
- [x] 跨文档一致性校验通过（术语、表名、字段、API 路径）
- [ ] 架构图 Mermaid 渲染校验（需用户人工确认）
- [ ] 用户评审通过关键方向与文档质量

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
