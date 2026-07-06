"""init schema

Revision ID: 001
Revises:
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "city",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("province", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "district",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["city_id"], ["city.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "area",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("code", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["district_id"], ["district.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "community",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("address", sa.String(200), nullable=True),
        sa.Column("year_built", sa.SmallInteger(), nullable=True),
        sa.Column("building_type", sa.String(30), nullable=True),
        sa.Column("total_units", sa.Integer(), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lng", sa.Numeric(10, 7), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "listing",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("community_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_id", sa.String(50), nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("unit_price", sa.Integer(), nullable=True),
        sa.Column("area_sqm", sa.Numeric(8, 2), nullable=True),
        sa.Column("layout", sa.String(30), nullable=True),
        sa.Column("floor", sa.String(30), nullable=True),
        sa.Column("orientation", sa.String(30), nullable=True),
        sa.Column("listed_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["community_id"], ["community.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_id", name="uq_listing_source"),
    )

    op.create_table(
        "price_snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("region_type", sa.String(10), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("year_month", sa.String(7), nullable=False),
        sa.Column("supply_price", sa.Integer(), nullable=True),
        sa.Column("attention_price", sa.Integer(), nullable=True),
        sa.Column("value_price", sa.Integer(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_type", "region_id", "year_month", name="uq_price_snapshot_region_month"),
    )
    op.create_index("idx_price_snapshot_region", "price_snapshot", ["region_type", "region_id"])
    op.create_index("idx_price_snapshot_month", "price_snapshot", ["year_month"])

    op.create_table(
        "price_distribution",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("region_type", sa.String(10), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("year_month", sa.String(7), nullable=False),
        sa.Column("price_range_low", sa.Integer(), nullable=False),
        sa.Column("price_range_high", sa.Integer(), nullable=False),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "region_type", "region_id", "year_month", "price_range_low",
            name="uq_price_distribution_region_range",
        ),
    )

    op.create_table(
        "prediction",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("region_type", sa.String(10), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("target_month", sa.String(7), nullable=False),
        sa.Column("predicted_price", sa.Integer(), nullable=False),
        sa.Column("confidence_lower", sa.Integer(), nullable=True),
        sa.Column("confidence_upper", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(20), nullable=False),
        sa.Column("features_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "region_type", "region_id", "target_month", "model_name", "model_version",
            name="uq_prediction_region_model",
        ),
    )

    op.create_table(
        "user_account",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role", sa.String(10), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "crawl_job",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("city_code", sa.String(20), nullable=False),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "crawl_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_path", sa.String(300), nullable=True),
        sa.Column("record_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["crawl_job.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_crawl_log_job", "crawl_log", ["job_id"])


def downgrade() -> None:
    op.drop_table("crawl_log")
    op.drop_table("crawl_job")
    op.drop_table("user_account")
    op.drop_table("prediction")
    op.drop_table("price_distribution")
    op.drop_index("idx_price_snapshot_month", "price_snapshot")
    op.drop_index("idx_price_snapshot_region", "price_snapshot")
    op.drop_table("price_snapshot")
    op.drop_table("listing")
    op.drop_table("community")
    op.drop_table("area")
    op.drop_table("district")
    op.drop_table("city")
