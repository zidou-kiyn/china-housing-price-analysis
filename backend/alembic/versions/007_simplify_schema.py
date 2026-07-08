"""精简数据库：删除无用表（area/community/listing/price_index_snapshot），清空历史数据

Revision ID: 007
Revises: 006
Create Date: 2026-07-08

creprice 采集管线从未写入 area/community/listing，NBS 指数功能已砍。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS area CASCADE")
    op.execute("DROP TABLE IF EXISTS community CASCADE")
    op.execute("DROP TABLE IF EXISTS listing CASCADE")
    op.execute("DROP TABLE IF EXISTS price_index_snapshot CASCADE")

    op.execute(
        "TRUNCATE TABLE district, price_snapshot, price_distribution, "
        "prediction, admin_job, crawl_job, crawl_log CASCADE"
    )
    op.execute("DELETE FROM app_setting")


def downgrade() -> None:
    op.create_table(
        "area",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["district_id"], ["district.id"]),
    )

    op.create_table(
        "community",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"]),
    )

    op.create_table(
        "listing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("community_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("unit_price", sa.Integer(), nullable=True),
        sa.Column("total_price", sa.Integer(), nullable=True),
        sa.Column("area_sqm", sa.Float(), nullable=True),
        sa.Column("layout", sa.String(50), nullable=True),
        sa.Column("floor", sa.String(50), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["community_id"], ["community.id"]),
    )

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
