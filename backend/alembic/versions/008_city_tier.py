"""city 表添加 tier 字段并从 seed 填充

Revision ID: 008
Revises: 007
Create Date: 2026-07-09

第一财经 2025 城市等级分类：1=一线, 2=新一线, 3=二线, 4=三线, 5=四线, 6=五线。
"""
from typing import Sequence, Union
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_PATH = Path(__file__).resolve().parents[2] / "app" / "seed" / "city_tier_seed.json"


def upgrade() -> None:
    op.add_column("city", sa.Column("tier", sa.SmallInteger(), nullable=True))

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    city_tiers = seed["cities"]

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM city")).fetchall()
    for city_id, name in rows:
        tier = city_tiers.get(name)
        if tier is not None:
            conn.execute(
                sa.text("UPDATE city SET tier = :tier WHERE id = :id"),
                {"tier": tier, "id": city_id},
            )


def downgrade() -> None:
    op.drop_column("city", "tier")
