"""Add durable revision-bound approval actions.

Revision ID: 20260823_0016
Revises: 20260823_0015
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0016"
down_revision: str | None = "20260823_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("post_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("transport", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="created"),
        sa.Column("selected_action", sa.String(length=30), nullable=True),
        sa.Column("remote_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.String(length=40), nullable=False),
        sa.Column("consumed_at", sa.String(length=40), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_actions_post_id", "approval_actions", ["post_id"])
    op.create_index("ix_approval_actions_transport", "approval_actions", ["transport"])
    op.create_index("ix_approval_actions_status", "approval_actions", ["status"])
    op.create_index("ix_approval_actions_created_at", "approval_actions", ["created_at"])
    op.create_index("ix_approval_actions_expires_at", "approval_actions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_approval_actions_expires_at", table_name="approval_actions")
    op.drop_index("ix_approval_actions_created_at", table_name="approval_actions")
    op.drop_index("ix_approval_actions_status", table_name="approval_actions")
    op.drop_index("ix_approval_actions_transport", table_name="approval_actions")
    op.drop_index("ix_approval_actions_post_id", table_name="approval_actions")
    op.drop_table("approval_actions")
