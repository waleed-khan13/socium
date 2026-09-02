"""Add website-discovered brand typography.

Revision ID: 20260824_0018
Revises: 20260823_0017
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0018"
down_revision: str | None = "20260823_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workspace", sa.Column("heading_font", sa.String(length=160), nullable=False, server_default=""))
    op.add_column("workspace", sa.Column("body_font", sa.String(length=160), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("workspace", "body_font")
    op.drop_column("workspace", "heading_font")
