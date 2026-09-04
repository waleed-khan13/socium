"""Add the local-first Business OS foundation.

Revision ID: 20260904_0022
Revises: 20260830_0021
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260904_0022"
down_revision: str | None = "20260830_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _workspace_table(name: str, *columns: sa.Column) -> None:
    op.create_table(
        name,
        *columns,
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
    )
    op.create_index(f"ix_{name}_workspace_id", name, ["workspace_id"])


def upgrade() -> None:
    _workspace_table(
        "business_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("facts", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("visual_profile", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confirmed_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("workspace_id", name="uq_business_profile_workspace"),
    )
    op.create_index("ix_business_profiles_status", "business_profiles", ["status"])

    _workspace_table(
        "knowledge_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("locator", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("last_checked_at", sa.String(length=40), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("workspace_id", "kind", "locator", name="uq_knowledge_source_locator"),
    )
    op.create_index("ix_knowledge_sources_kind", "knowledge_sources", ["kind"])
    op.create_index("ix_knowledge_sources_status", "knowledge_sources", ["status"])

    _workspace_table(
        "knowledge_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("fact_key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="proposed"),
        sa.Column("source_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("verified_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_sources.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_knowledge_items_source_id", "knowledge_items", ["source_id"])
    op.create_index("ix_knowledge_items_fact_key", "knowledge_items", ["fact_key"])
    op.create_index("ix_knowledge_items_status", "knowledge_items", ["status"])

    _workspace_table(
        "preference_memories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("workspace_id", "category", "key", name="uq_preference_memory_key"),
    )
    op.create_index("ix_preference_memories_category", "preference_memories", ["category"])
    op.create_index("ix_preference_memories_status", "preference_memories", ["status"])

    _workspace_table(
        "workflow_definitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("approval_mode", sa.String(length=30), nullable=False, server_default="approval_required"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
    )
    op.create_index("ix_workflow_definitions_kind", "workflow_definitions", ["kind"])
    op.create_index("ix_workflow_definitions_enabled", "workflow_definitions", ["enabled"])
    op.create_index("ix_workflow_definitions_approval_mode", "workflow_definitions", ["approval_mode"])

    _workspace_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workflow_id", sa.String(length=36), nullable=True),
        sa.Column("trigger", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("input_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("output_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.String(length=40), nullable=True),
        sa.Column("completed_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_definitions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("ix_workflow_runs_trigger", "workflow_runs", ["trigger"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_created_at", "workflow_runs", ["created_at"])

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("input_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("output_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.String(length=40), nullable=True),
        sa.Column("completed_at", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "position", name="uq_workflow_step_position"),
    )
    op.create_index("ix_workflow_steps_run_id", "workflow_steps", ["run_id"])
    op.create_index("ix_workflow_steps_kind", "workflow_steps", ["kind"])
    op.create_index("ix_workflow_steps_status", "workflow_steps", ["status"])

    _workspace_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("subject_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("allowed_actions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("decided_action", sa.String(length=30), nullable=True),
        sa.Column("decided_by", sa.String(length=160), nullable=True),
        sa.Column("decision_source", sa.String(length=30), nullable=True),
        sa.Column("expires_at", sa.String(length=40), nullable=True),
        sa.Column("decided_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint(
            "workspace_id", "subject_type", "subject_id", "subject_revision",
            name="uq_approval_request_subject_revision",
        ),
    )
    for column in ("subject_type", "subject_id", "status", "expires_at", "created_at"):
        op.create_index(f"ix_approval_requests_{column}", "approval_requests", [column])

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("approval_request_id", sa.String(length=36), nullable=False),
        sa.Column("transport", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("remote_ref", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("approval_request_id", "transport", name="uq_notification_delivery_transport"),
    )
    op.create_index(
        "ix_notification_deliveries_approval_request_id",
        "notification_deliveries",
        ["approval_request_id"],
    )
    op.create_index("ix_notification_deliveries_transport", "notification_deliveries", ["transport"])
    op.create_index("ix_notification_deliveries_status", "notification_deliveries", ["status"])

    _workspace_table(
        "inbox_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("entity_type", sa.String(length=40), nullable=True),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("action_url", sa.String(length=2048), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_inbox_items_dedupe_key"),
    )
    for column in ("kind", "priority", "status", "entity_type", "entity_id", "dedupe_key", "created_at"):
        op.create_index(f"ix_inbox_items_{column}", "inbox_items", [column])

    _workspace_table(
        "ai_decision_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("purpose", sa.String(length=80), nullable=False),
        sa.Column("provider_kind", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=180), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False, server_default="v1"),
        sa.Column("context_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_micros", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
    )
    for column in ("purpose", "provider_kind", "status", "created_at"):
        op.create_index(f"ix_ai_decision_logs_{column}", "ai_decision_logs", [column])

    op.execute(
        """
        CREATE VIRTUAL TABLE knowledge_items_fts USING fts5(
            fact_key,
            value,
            source_excerpt,
            content='knowledge_items',
            content_rowid='rowid'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_items_ai AFTER INSERT ON knowledge_items BEGIN
            INSERT INTO knowledge_items_fts(rowid, fact_key, value, source_excerpt)
            VALUES (new.rowid, new.fact_key, new.value, new.source_excerpt);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_items_ad AFTER DELETE ON knowledge_items BEGIN
            INSERT INTO knowledge_items_fts(knowledge_items_fts, rowid, fact_key, value, source_excerpt)
            VALUES ('delete', old.rowid, old.fact_key, old.value, old.source_excerpt);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_items_au AFTER UPDATE ON knowledge_items BEGIN
            INSERT INTO knowledge_items_fts(knowledge_items_fts, rowid, fact_key, value, source_excerpt)
            VALUES ('delete', old.rowid, old.fact_key, old.value, old.source_excerpt);
            INSERT INTO knowledge_items_fts(rowid, fact_key, value, source_excerpt)
            VALUES (new.rowid, new.fact_key, new.value, new.source_excerpt);
        END
        """
    )

    op.execute(
        """
        INSERT INTO business_profiles (
            id, workspace_id, revision, status, facts, visual_profile,
            confirmed_at, created_at, updated_at
        )
        SELECT
            lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' ||
            lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' ||
            lower(hex(randomblob(6))),
            id,
            CASE WHEN profile_version > 0 THEN profile_version ELSE 1 END,
            CASE WHEN confirmed_at IS NULL THEN 'draft' ELSE 'confirmed' END,
            json_object(
                'workspaceName', name, 'businessName', business_name, 'description', description,
                'timezone', timezone, 'website', website, 'industry', industry,
                'productsServices', products_services, 'targetAudience', target_audience,
                'location', location, 'goals', json(goals), 'callToAction', call_to_action,
                'language', language, 'tone', tone, 'contentPillars', json(content_pillars),
                'restrictedClaims', json(restricted_claims), 'brandedHashtags', json(branded_hashtags)
            ),
            json_object(
                'logoMediaId', logo_media_id, 'referenceMediaIds', json(reference_media_ids),
                'primaryColor', primary_color, 'secondaryColor', secondary_color,
                'accentColor', accent_color, 'headingFont', heading_font,
                'bodyFont', body_font, 'visualStyle', visual_style
            ),
            confirmed_at,
            COALESCE(updated_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            COALESCE(updated_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        FROM workspace
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS knowledge_items_au")
    op.execute("DROP TRIGGER IF EXISTS knowledge_items_ad")
    op.execute("DROP TRIGGER IF EXISTS knowledge_items_ai")
    op.execute("DROP TABLE IF EXISTS knowledge_items_fts")
    for table in (
        "ai_decision_logs",
        "inbox_items",
        "notification_deliveries",
        "approval_requests",
        "workflow_steps",
        "workflow_runs",
        "workflow_definitions",
        "preference_memories",
        "knowledge_items",
        "knowledge_sources",
        "business_profiles",
    ):
        op.drop_table(table)
