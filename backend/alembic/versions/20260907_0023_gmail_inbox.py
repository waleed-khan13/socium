"""Add Gmail threads and approved reply drafts.

Revision ID: 20260907_0023
Revises: 20260904_0022
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260907_0023"
down_revision: str | None = "20260904_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_threads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("connector_account_id", sa.String(length=36), nullable=False),
        sa.Column("provider_thread_id", sa.String(length=255), nullable=False),
        sa.Column("history_id", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=998), nullable=False, server_default=""),
        sa.Column("snippet", sa.Text(), nullable=False, server_default=""),
        sa.Column("sender_name", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("sender_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("participants", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("classification", sa.String(length=40), nullable=False, server_default="needs_review"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("unread", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_message_at", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connector_account_id"], ["connector_accounts.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "connector_account_id",
            "provider_thread_id",
            name="uq_email_thread_provider_identity",
        ),
    )
    for column in (
        "workspace_id",
        "connector_account_id",
        "classification",
        "priority",
        "status",
        "unread",
        "last_message_at",
    ):
        op.create_index(f"ix_email_threads_{column}", "email_threads", [column])

    op.create_table(
        "email_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("internet_message_id", sa.String(length=998), nullable=False, server_default=""),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("sender", sa.String(length=998), nullable=False, server_default=""),
        sa.Column("recipients", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("subject", sa.String(length=998), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("snippet", sa.Text(), nullable=False, server_default=""),
        sa.Column("references", sa.Text(), nullable=False, server_default=""),
        sa.Column("sent_at", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["email_threads.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("thread_id", "provider_message_id", name="uq_email_message_provider_identity"),
    )
    for column in ("thread_id", "direction", "sent_at"):
        op.create_index(f"ix_email_messages_{column}", "email_messages", [column])

    op.create_table(
        "email_reply_drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("approval_request_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("subject", sa.String(length=998), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("classification", sa.String(length=40), nullable=False, server_default="needs_reply"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("scheduled_for", sa.String(length=40), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("sent_at", sa.String(length=40), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["email_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["approval_request_id"], ["approval_requests.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("thread_id", "revision", name="uq_email_reply_revision"),
    )
    for column in ("thread_id", "approval_request_id", "status", "scheduled_for", "created_at"):
        op.create_index(f"ix_email_reply_drafts_{column}", "email_reply_drafts", [column])


def downgrade() -> None:
    op.drop_table("email_reply_drafts")
    op.drop_table("email_messages")
    op.drop_table("email_threads")
