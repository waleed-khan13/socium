"""Attach local generated media to versioned post packages.

Revision ID: 20260830_0021
Revises: 20260827_0020
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0021"
down_revision: str | None = "20260827_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("posts") as batch:
        batch.add_column(sa.Column("media_asset_id", sa.String(length=36), nullable=True))
        batch.create_index("ix_posts_media_asset_id", ["media_asset_id"])
        batch.create_foreign_key(
            "fk_posts_media_asset_id",
            "media_assets",
            ["media_asset_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("posts") as batch:
        batch.drop_constraint("fk_posts_media_asset_id", type_="foreignkey")
        batch.drop_index("ix_posts_media_asset_id")
        batch.drop_column("media_asset_id")
