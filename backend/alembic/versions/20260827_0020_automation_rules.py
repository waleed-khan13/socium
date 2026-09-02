"""Add recurring social automation rules.

Revision ID: 20260827_0020
Revises: 20260826_0019
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_0020"
down_revision: str | None = "20260826_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("tone", sa.String(length=160), nullable=False),
        sa.Column("objective", sa.String(length=500), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("days_of_week", sa.JSON(), nullable=False),
        sa.Column("publish_time", sa.String(length=5), nullable=False),
        sa.Column("approval_channels", sa.JSON(), nullable=False),
        sa.Column("generate_ahead_minutes", sa.Integer(), nullable=False),
        sa.Column("publish_after_approval", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.String(length=40), nullable=True),
        sa.Column("next_publish_at", sa.String(length=40), nullable=True),
        sa.Column("last_run_at", sa.String(length=40), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_rules_enabled", "automation_rules", ["enabled"])
    op.create_index("ix_automation_rules_next_run_at", "automation_rules", ["next_run_at"])
    with op.batch_alter_table("posts") as batch:
        batch.add_column(sa.Column("automation_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("automation_publish_at", sa.String(length=40), nullable=True))
        batch.create_index("ix_posts_automation_id", ["automation_id"])
        batch.create_index("ix_posts_automation_publish_at", ["automation_publish_at"])
        batch.create_foreign_key(
            "fk_posts_automation_id",
            "automation_rules",
            ["automation_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("posts") as batch:
        batch.drop_constraint("fk_posts_automation_id", type_="foreignkey")
        batch.drop_index("ix_posts_automation_publish_at")
        batch.drop_index("ix_posts_automation_id")
        batch.drop_column("automation_publish_at")
        batch.drop_column("automation_id")
    op.drop_index("ix_automation_rules_next_run_at", table_name="automation_rules")
    op.drop_index("ix_automation_rules_enabled", table_name="automation_rules")
    op.drop_table("automation_rules")
