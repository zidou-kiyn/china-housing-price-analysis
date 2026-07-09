"""district 唯一键改为 (city_id, code) 复合唯一并清空业务数据

Revision ID: 009
Revises: 008
Create Date: 2026-07-09

原 `district.code` 全局唯一导致短码冲突：不同城市共用"高新区(G1)/经开区(J1)/丰泽区(FZ)"等短码时，
seed 加载被 ON CONFLICT DO NOTHING 静默跳过，数据错位塞到别的城市 district_id 上。
本迁移彻底重置：清空业务数据、改复合唯一约束，让下次启动 seed 干净重导。user_account 与
city（cities.json 灌入的城市字典 + 008 灌入的 tier）予以保留。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "TRUNCATE TABLE district, price_snapshot, price_distribution, "
        "prediction, admin_job, crawl_job, crawl_log CASCADE"
    )
    op.execute("DELETE FROM app_setting WHERE key = 'seed_price_version'")

    op.drop_constraint("district_code_key", "district", type_="unique")
    op.create_unique_constraint(
        "uq_district_city_code", "district", ["city_id", "code"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_district_city_code", "district", type_="unique")
    op.create_unique_constraint("district_code_key", "district", ["code"])
