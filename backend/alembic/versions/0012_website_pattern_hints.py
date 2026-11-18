"""AI-2 historical pattern hints per website.

Revision ID: 0012_website_pattern_hints
Revises: 0011_website_scenarios
Create Date: 2026-11-16

One stored hint set per website. Reuse is gated by window + sample_limit +
based_on_latest_check_id so a new check invalidates the cache. schedule/AI
auto-runs are out of scope.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_website_pattern_hints"
down_revision = "0011_website_scenarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "website_pattern_hints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("window", sa.String(length=8), nullable=False),
        sa.Column("sample_limit", sa.Integer(), nullable=False),
        sa.Column("check_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("based_on_latest_check_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.String(length=800), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("patterns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "confirmed_observations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "recommended_investigation_steps",
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
            '"window" IN (\'24h\', \'7d\', \'all\')',
            name="ck_website_pattern_hints_window",
        ),
        sa.CheckConstraint(
            "sample_limit >= 1 AND sample_limit <= 200",
            name="ck_website_pattern_hints_sample_limit",
        ),
        sa.CheckConstraint(
            "check_count >= 0 AND failure_count >= 0 AND failure_count <= check_count",
            name="ck_website_pattern_hints_counts",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_website_pattern_hints_severity",
        ),
        sa.CheckConstraint(
            "provider IN ('simulated', 'openai')",
            name="ck_website_pattern_hints_provider",
        ),
        sa.CheckConstraint(
            "char_length(btrim(summary)) >= 1",
            name="ck_website_pattern_hints_summary_not_blank",
        ),
        sa.CheckConstraint(
            "char_length(btrim(limitations)) >= 1",
            name="ck_website_pattern_hints_limitations_not_blank",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["based_on_latest_check_id"],
            ["website_checks.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", name="uq_website_pattern_hints_website_id"),
    )
    op.create_index(
        "ix_website_pattern_hints_website_id_created_at",
        "website_pattern_hints",
        ["website_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_website_pattern_hints_website_id_created_at",
        table_name="website_pattern_hints",
    )
    op.drop_table("website_pattern_hints")
