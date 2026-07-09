# M1-2 数据库模型与迁移

## Goal

实现 `docs/04-数据模型与数据库设计.md` 定义的全部 SQLAlchemy ORM 模型，配置 Alembic 迁移框架，生成初始迁移脚本。

## Requirements

- 实现 11 个 SQLAlchemy 模型：city / district / area / community / listing / price_snapshot / price_distribution / prediction / user_account / crawl_job / crawl_log
- 所有模型继承 `app.core.database.Base`
- 字段类型、约束、索引严格对齐 `docs/04-数据模型与数据库设计.md` DDL
- 配置 Alembic，使用 async engine
- 生成初始迁移脚本

## Acceptance Criteria

- [ ] 所有 11 个模型可正常导入
- [ ] Alembic 配置完成，`alembic revision --autogenerate` 可生成迁移
- [ ] 迁移脚本可在 PostgreSQL 上执行（`alembic upgrade head`）
- [ ] 唯一约束和索引与 docs/04 一致

## Dependencies

依赖 M1-1（infra-scaffold）的项目结构和数据库连接配置。
