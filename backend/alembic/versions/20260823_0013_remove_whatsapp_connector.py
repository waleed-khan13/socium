"""Remove legacy WhatsApp connector accounts.

Revision ID: 20260823_0013
Revises: 20260810_0012
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0013"
down_revision: str | None = "20260810_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text("DELETE FROM connector_accounts WHERE adapter_id = :adapter_id").bindparams(
            adapter_id="whatsapp"
        )
    )


def downgrade() -> None:
    # Deleted credentials cannot be reconstructed safely during a runtime rollback.
    pass
