"""Add durable worker leases and overdue recovery state.

Revision ID: 20260823_0017
Revises: 20260823_0016
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0017"
down_revision: str | None = "20260823_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("local_jobs", sa.Column("lease_token", sa.String(length=36), nullable=True))
    op.add_column("local_jobs", sa.Column("lease_expires_at", sa.String(length=40), nullable=True))
    op.add_column("local_jobs", sa.Column("recovery_required_at", sa.String(length=40), nullable=True))
    op.add_column("local_jobs", sa.Column("recovery_reason", sa.String(length=500), nullable=True))
    op.create_index("ix_local_jobs_lease_token", "local_jobs", ["lease_token"])
    op.create_index("ix_local_jobs_lease_expires_at", "local_jobs", ["lease_expires_at"])
    op.create_index("ix_local_jobs_recovery_required_at", "local_jobs", ["recovery_required_at"])


def downgrade() -> None:
    op.drop_index("ix_local_jobs_recovery_required_at", table_name="local_jobs")
    op.drop_index("ix_local_jobs_lease_expires_at", table_name="local_jobs")
    op.drop_index("ix_local_jobs_lease_token", table_name="local_jobs")
    op.drop_column("local_jobs", "recovery_reason")
    op.drop_column("local_jobs", "recovery_required_at")
    op.drop_column("local_jobs", "lease_expires_at")
    op.drop_column("local_jobs", "lease_token")
