"""price_snapshot 多源独立存储：唯一约束加入 source

Revision ID: 005
Revises: 004
Create Date: 2026-07-08

口径治理：latest-wins 曾使 58 年度挂牌覆盖北京 kaggle 成交 12 月点。改为
(region_type, region_id, year_month, source) 唯一——各源序列独立共存，写入
永不跨源覆盖，冲突解决移到读取层（app/core/source_policy.py 优先级）。

downgrade 有损：每 (region, month) 仅保留优先级最高的行，删除其余后恢复旧约束。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 004 前的历史行可能仍为 NULL（当时唯一源是 creprice）；NOT NULL 前幂等回填
    op.execute("UPDATE price_snapshot SET source = 'creprice' WHERE source IS NULL")
    op.alter_column("price_snapshot", "source", existing_type=sa.String(20), nullable=False)
    op.drop_constraint("uq_price_snapshot_region_month", "price_snapshot", type_="unique")
    op.create_unique_constraint(
        "uq_price_snapshot_region_month_source",
        "price_snapshot",
        ["region_type", "region_id", "year_month", "source"],
    )


def downgrade() -> None:
    # 有损：按源优先级（月度 > 年度挂牌）每 (region, month) 保留一行
    op.execute(
        """
        DELETE FROM price_snapshot ps USING (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY region_type, region_id, year_month
                ORDER BY CASE source
                    WHEN 'creprice' THEN 0
                    WHEN 'kaggle_lianjia' THEN 1
                    WHEN 'listing_annual_58' THEN 2
                    WHEN 'listing_annual_anjuke' THEN 3
                    ELSE 9
                END
            ) AS rn
            FROM price_snapshot
        ) ranked
        WHERE ps.id = ranked.id AND ranked.rn > 1
        """
    )
    op.drop_constraint("uq_price_snapshot_region_month_source", "price_snapshot", type_="unique")
    op.create_unique_constraint(
        "uq_price_snapshot_region_month",
        "price_snapshot",
        ["region_type", "region_id", "year_month"],
    )
    op.alter_column("price_snapshot", "source", existing_type=sa.String(20), nullable=True)
