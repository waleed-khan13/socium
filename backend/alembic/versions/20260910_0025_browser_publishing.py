"""Add local browser accounts and durable publish intent without replacing posts."""

import sqlalchemy as sa

from alembic import op

revision = "20260910_0025"
down_revision = "20260908_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_browser_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("identity", sa.String(500)),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("preferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("last_verified_at", sa.String(40)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_social_browser_accounts_platform", "social_browser_accounts", ["platform"])
    op.create_table(
        "browser_publish_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(200), nullable=False, unique=True),
        sa.Column("post_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("step", sa.String(80), nullable=False),
        sa.Column("adapter_version", sa.String(40), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("remote_url", sa.String(2048)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    for column in ("post_id", "account_id"):
        op.create_index(f"ix_browser_publish_attempts_{column}", "browser_publish_attempts", [column])
    op.add_column("posts", sa.Column("browser_account_id", sa.String(36)))
    op.add_column("posts", sa.Column("browser_account_name", sa.String(160)))
    op.add_column("posts", sa.Column("browser_account_identity", sa.String(500)))
    op.create_index("ix_posts_browser_account_id", "posts", ["browser_account_id"])


def downgrade() -> None:
    op.drop_index("ix_posts_browser_account_id", "posts")
    with op.batch_alter_table("posts") as batch:
        batch.drop_column("browser_account_identity")
        batch.drop_column("browser_account_name")
        batch.drop_column("browser_account_id")
    op.drop_table("browser_publish_attempts")
    op.drop_table("social_browser_accounts")
