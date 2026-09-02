"""Add encrypted Telegram proxy settings.

Revision ID: 20260826_0019
Revises: 20260824_0018
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260826_0019"
down_revision: str | None = "20260824_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("telegram_settings", sa.Column("proxy_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("telegram_settings", "proxy_url")
