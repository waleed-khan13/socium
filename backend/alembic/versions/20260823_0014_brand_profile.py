"""Add the durable brand profile and content preferences.

Revision ID: 20260823_0014
Revises: 20260823_0013
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0014"
down_revision: str | None = "20260823_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = (
        sa.Column("website", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("industry", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("products_services", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_audience", sa.Text(), nullable=False, server_default=""),
        sa.Column("location", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("goals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("call_to_action", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=80), nullable=False, server_default="English"),
        sa.Column("tone", sa.String(length=240), nullable=False, server_default="Clear and confident"),
        sa.Column("content_pillars", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("restricted_claims", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("branded_hashtags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("logo_media_id", sa.String(length=36), nullable=True),
        sa.Column("reference_media_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("primary_color", sa.String(length=7), nullable=False, server_default="#f59e0b"),
        sa.Column("secondary_color", sa.String(length=7), nullable=False, server_default="#18181b"),
        sa.Column("accent_color", sa.String(length=7), nullable=False, server_default="#10b981"),
        sa.Column("visual_style", sa.Text(), nullable=False, server_default=""),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed_at", sa.String(length=40), nullable=True),
        sa.Column("updated_at", sa.String(length=40), nullable=True),
    )
    for column in columns:
        op.add_column("workspace", column)


def downgrade() -> None:
    for column in reversed(
        (
            "website",
            "industry",
            "products_services",
            "target_audience",
            "location",
            "goals",
            "call_to_action",
            "language",
            "tone",
            "content_pillars",
            "restricted_claims",
            "branded_hashtags",
            "logo_media_id",
            "reference_media_ids",
            "primary_color",
            "secondary_color",
            "accent_color",
            "visual_style",
            "profile_version",
            "confirmed_at",
            "updated_at",
        )
    ):
        op.drop_column("workspace", column)
