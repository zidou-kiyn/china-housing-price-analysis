"""price_snapshot.source 溯源注记列

Revision ID: 004
Revises: 003
Create Date: 2026-07-08

多源采集：给 price_snapshot 增加可空 source 列，记录该行最后写入的数据源。
不进唯一约束（latest-wins），读点零改动。历史行幂等回填当前唯一源 creprice。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("price_snapshot", sa.Column("source", sa.String(20), nullable=True))
    op.execute("UPDATE price_snapshot SET source = 'creprice' WHERE source IS NULL")


def downgrade() -> None:
    op.drop_column("price_snapshot", "source")
