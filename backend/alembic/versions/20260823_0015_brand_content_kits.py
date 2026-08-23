"""Add structured brand content kits to posts.

Revision ID: 20260823_0015
Revises: 20260823_0014
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0015"
down_revision: str | None = "20260823_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("call_to_action", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("image_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_negative_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_alt_text", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("brand_profile_version", sa.Integer(), nullable=False, server_default="0"),
    ):
        op.add_column("posts", column)


def downgrade() -> None:
    for column in (
        "brand_profile_version",
        "image_alt_text",
        "image_negative_prompt",
        "image_prompt",
        "call_to_action",
    ):
        op.drop_column("posts", column)
