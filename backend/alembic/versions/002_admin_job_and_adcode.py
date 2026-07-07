"""admin_job table + city.adcode

Revision ID: 002
Revises: 001
Create Date: 2026-07-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_job",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("progress_done", sa.Integer(), server_default="0", nullable=False),
        sa.Column("progress_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_admin_job_active_kind",
        "admin_job",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )

    op.add_column("city", sa.Column("adcode", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("city", "adcode")
    op.drop_index("uq_admin_job_active_kind", table_name="admin_job")
    op.drop_table("admin_job")
