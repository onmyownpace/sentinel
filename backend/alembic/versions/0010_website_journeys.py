"""BROW-2 declarative journeys and run history.

Revision ID: 0010_website_journeys
Revises: 0009_check_screenshots
Create Date: 2026-11-16

Journeys are stored separately from one-shot website_checks. Steps are JSON
(navigate / fill / click / assert_*). Runs record per-step outcomes.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_website_journeys"
down_revision = "0009_check_screenshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "website_journeys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("char_length(btrim(name)) >= 1", name="ck_website_journeys_name_not_blank"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_website_journeys_website_id_created_at",
        "website_journeys",
        ["website_id", "created_at"],
    )

    op.create_table(
        "journey_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("journey_id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("step_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'failed')",
            name="ck_journey_runs_outcome",
        ),
        sa.CheckConstraint(
            "duration_ms >= 0 AND duration_ms <= 180000",
            name="ck_journey_runs_duration",
        ),
        sa.ForeignKeyConstraint(["journey_id"], ["website_journeys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_journey_runs_journey_id_created_at",
        "journey_runs",
        ["journey_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_journey_runs_journey_id_created_at", table_name="journey_runs")
    op.drop_table("journey_runs")
    op.drop_index("ix_website_journeys_website_id_created_at", table_name="website_journeys")
    op.drop_table("website_journeys")
