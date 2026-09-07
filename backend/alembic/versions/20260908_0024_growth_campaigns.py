"""Normalize leads and add consent-aware campaigns.

Revision ID: 20260908_0024
Revises: 20260907_0023
Create Date: 2026-09-08
"""

from collections.abc import Sequence
from urllib.parse import urlsplit
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260908_0024"
down_revision: str | None = "20260907_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _domain(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    return (parsed.hostname or "").strip(".").lower().removeprefix("www.")


def _text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("normalized_key", sa.String(length=512), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String(length=2048), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "normalized_key", name="uq_company_workspace_key"),
    )
    for column in ("workspace_id", "domain", "source", "created_at", "updated_at"):
        op.create_index(f"ix_companies_{column}", "companies", [column])

    op.create_table(
        "contacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("normalized_key", sa.String(length=512), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("job_title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String(length=2048), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="new"),
        sa.Column("suppressed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("suppression_reason", sa.String(length=500), nullable=True),
        sa.Column("suppressed_at", sa.String(length=40), nullable=True),
        sa.Column("consent_status", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("legal_basis", sa.String(length=60), nullable=True),
        sa.Column("legal_basis_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("retention_until", sa.String(length=10), nullable=True),
        sa.Column("compliance_reviewed_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("workspace_id", "normalized_key", name="uq_contact_workspace_key"),
    )
    for column in (
        "workspace_id", "company_id", "email", "source", "status", "suppressed",
        "consent_status", "legal_basis", "retention_until", "created_at", "updated_at",
    ):
        op.create_index(f"ix_contacts_{column}", "contacts", [column])

    with op.batch_alter_table("leads") as batch:
        batch.add_column(sa.Column("company_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("contact_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_leads_company_id", "companies", ["company_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_leads_contact_id", "contacts", ["contact_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_leads_company_id", ["company_id"])
        batch.create_index("ix_leads_contact_id", ["contact_id"])

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT * FROM leads ORDER BY created_at, id")).mappings().all()
    companies: dict[str, str] = {}
    contacts: dict[str, str] = {}
    for lead in rows:
        domain = _domain(lead["website"])
        normalized_name = _text(lead["business_name"])
        company_key = (
            f"domain:{domain}"
            if domain
            else (f"name:{normalized_name}|{_text(lead['location'])}" if normalized_name else f"lead:{lead['id']}")
        )
        company_id = companies.get(company_key)
        if company_id is None:
            company_id = str(uuid4())
            companies[company_key] = company_id
            connection.execute(
                sa.text(
                    "INSERT INTO companies (id, workspace_id, name, normalized_key, domain, website, location, "
                    "source, source_ref, evidence, created_at, updated_at) VALUES "
                    "(:id, 1, :name, :key, :domain, :website, :location, :source, :source_ref, :evidence, :created_at, :updated_at)"
                ),
                {
                    "id": company_id, "name": lead["business_name"] or "", "key": company_key,
                    "domain": domain or None, "website": lead["website"], "location": lead["location"],
                    "source": lead["source"], "source_ref": lead["source_ref"],
                    "evidence": lead["evidence"] or "[]", "created_at": lead["created_at"],
                    "updated_at": lead["updated_at"],
                },
            )
        email = _text(lead["email"])
        phone = "".join(character for character in (lead["phone"] or "") if character.isdigit())
        contact_key = f"email:{email}" if email else (f"phone:{phone}" if phone else f"lead:{lead['id']}")
        contact_id = contacts.get(contact_key)
        if contact_id is None:
            contact_id = str(uuid4())
            contacts[contact_key] = contact_id
            connection.execute(
                sa.text(
                    "INSERT INTO contacts (id, workspace_id, company_id, normalized_key, full_name, job_title, email, phone, "
                    "source, source_ref, evidence, status, suppressed, suppression_reason, suppressed_at, consent_status, "
                    "legal_basis, legal_basis_note, retention_until, compliance_reviewed_at, created_at, updated_at) VALUES "
                    "(:id, 1, :company_id, :key, '', '', :email, :phone, :source, :source_ref, :evidence, :status, :suppressed, "
                    ":suppression_reason, :suppressed_at, :consent_status, :legal_basis, :legal_basis_note, :retention_until, "
                    ":compliance_reviewed_at, :created_at, :updated_at)"
                ),
                {
                    "id": contact_id, "company_id": company_id, "key": contact_key, "email": lead["email"],
                    "phone": lead["phone"], "source": lead["source"], "source_ref": lead["source_ref"],
                    "evidence": lead["evidence"] or "[]", "status": lead["status"],
                    "suppressed": lead["suppressed"], "suppression_reason": lead["suppression_reason"],
                    "suppressed_at": lead["suppressed_at"], "consent_status": lead["consent_status"],
                    "legal_basis": lead["legal_basis"], "legal_basis_note": lead["legal_basis_note"],
                    "retention_until": lead["retention_until"], "compliance_reviewed_at": lead["compliance_reviewed_at"],
                    "created_at": lead["created_at"], "updated_at": lead["updated_at"],
                },
            )
        connection.execute(
            sa.text("UPDATE leads SET company_id = :company_id, contact_id = :contact_id WHERE id = :lead_id"),
            {"company_id": company_id, "contact_id": contact_id, "lead_id": lead["id"]},
        )

    op.create_table(
        "lead_campaigns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("objective", sa.String(length=500), nullable=False),
        sa.Column("tone", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("stop_on_reply", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("stop_on_consent_change", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("activated_at", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
    )
    for column in ("workspace_id", "status", "created_at"):
        op.create_index(f"ix_lead_campaigns_{column}", "lead_campaigns", [column])

    op.create_table(
        "campaign_steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("wait_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("subject_template", sa.String(length=200), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["lead_campaigns.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("campaign_id", "position", name="uq_campaign_step_position"),
    )
    op.create_index("ix_campaign_steps_campaign_id", "campaign_steps", ["campaign_id"])

    op.create_table(
        "campaign_members",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("contact_id", sa.String(length=36), nullable=False),
        sa.Column("lead_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stop_reason", sa.String(length=500), nullable=True),
        sa.Column("last_draft_id", sa.String(length=36), nullable=True),
        sa.Column("next_action_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["lead_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_draft_id"], ["outreach_drafts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_member_contact"),
    )
    for column in ("campaign_id", "contact_id", "lead_id", "status", "next_action_at"):
        op.create_index(f"ix_campaign_members_{column}", "campaign_members", [column])


def downgrade() -> None:
    op.drop_table("campaign_members")
    op.drop_table("campaign_steps")
    op.drop_table("lead_campaigns")
    with op.batch_alter_table("leads") as batch:
        batch.drop_index("ix_leads_contact_id")
        batch.drop_index("ix_leads_company_id")
        batch.drop_constraint("fk_leads_contact_id", type_="foreignkey")
        batch.drop_constraint("fk_leads_company_id", type_="foreignkey")
        batch.drop_column("contact_id")
        batch.drop_column("company_id")
    op.drop_table("contacts")
    op.drop_table("companies")
