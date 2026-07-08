"""price_index_snapshot 房价指数表（NBS 70 城月度指数落库）

Revision ID: 006
Revises: 005
Create Date: 2026-07-08

指数是 100 基准的 float，且一城一月多口径（新建/二手 × 环比/同比/定基），
与 PriceSnapshot 的「元/㎡ 整数」语义不同，独立建表（govstats.md §8.1）。
唯一键含全部口径维度 + source。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_index_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_type", sa.String(10), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("year_month", sa.String(7), nullable=False),
        sa.Column("dwelling_type", sa.String(10), nullable=False),
        sa.Column("base_type", sa.String(10), nullable=False),
        sa.Column("index_value", sa.Float(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "region_type", "region_id", "year_month",
            "dwelling_type", "base_type", "source",
            name="uq_price_index_region_month_kind_source",
        ),
    )
    op.create_index(
        "idx_price_index_region", "price_index_snapshot", ["region_type", "region_id"]
    )
    op.create_index("idx_price_index_month", "price_index_snapshot", ["year_month"])


def downgrade() -> None:
    op.drop_index("idx_price_index_month", table_name="price_index_snapshot")
    op.drop_index("idx_price_index_region", table_name="price_index_snapshot")
    op.drop_table("price_index_snapshot")
