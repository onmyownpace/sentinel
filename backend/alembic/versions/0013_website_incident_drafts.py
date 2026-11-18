"""AI-3 incident summary drafts from recent failed checks + analyses.

Revision ID: 0013_website_incident_drafts
Revises: 0012_website_pattern_hints
Create Date: 2026-11-16

Webhook-friendly JSON drafts for one-click UI or n8n automation. Simulated
default; OpenAI optional via ANALYSIS_PROVIDER. Not auto-run on every failure.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_website_incident_drafts"
down_revision = "0012_website_pattern_hints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "website_incident_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("failed_check_limit", sa.Integer(), nullable=False),
        sa.Column("failed_check_count", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "check_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "analysis_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("website_name", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("paragraph", sa.String(length=4000), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column(
            "observations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("limitations", sa.String(length=800), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "failed_check_limit >= 1 AND failed_check_limit <= 20",
            name="ck_website_incident_drafts_limit",
        ),
        sa.CheckConstraint(
            "failed_check_count >= 1 AND failed_check_count <= failed_check_limit",
            name="ck_website_incident_drafts_count",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_website_incident_drafts_severity",
        ),
        sa.CheckConstraint(
            "provider IN ('simulated', 'openai')",
            name="ck_website_incident_drafts_provider",
        ),
        sa.CheckConstraint(
            "char_length(btrim(paragraph)) >= 1",
            name="ck_website_incident_drafts_paragraph_not_blank",
        ),
        sa.CheckConstraint(
            "char_length(btrim(text)) >= 1",
            name="ck_website_incident_drafts_text_not_blank",
        ),
        sa.CheckConstraint(
            "char_length(btrim(limitations)) >= 1",
            name="ck_website_incident_drafts_limitations_not_blank",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_website_incident_drafts_website_id_created_at",
        "website_incident_drafts",
        ["website_id", "created_at"],
    )
    op.create_index(
        "ix_website_incident_drafts_website_fingerprint",
        "website_incident_drafts",
        ["website_id", "source_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_website_incident_drafts_website_fingerprint",
        table_name="website_incident_drafts",
    )
    op.drop_index(
        "ix_website_incident_drafts_website_id_created_at",
        table_name="website_incident_drafts",
    )
    op.drop_table("website_incident_drafts")
