"""BROW-3 named scenario library entries (wrap BROW-2 journeys).

Revision ID: 0011_website_scenarios
Revises: 0010_website_journeys
Create Date: 2026-11-16

A scenario is a reusable named library item attached to a website. It points at
an existing journey for steps. schedule_eligible is reserved for later n8n
enrollment and is not wired to a schedule in this milestone.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_website_scenarios"
down_revision = "0010_website_journeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "website_scenarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("journey_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "schedule_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
        sa.CheckConstraint(
            "char_length(btrim(name)) >= 1",
            name="ck_website_scenarios_name_not_blank",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["journey_id"], ["website_journeys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", "name", name="uq_website_scenarios_website_name"),
    )
    op.create_index(
        "ix_website_scenarios_website_id_created_at",
        "website_scenarios",
        ["website_id", "created_at"],
    )

    op.create_table(
        "scenario_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("journey_id", sa.Uuid(), nullable=False),
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
            name="ck_scenario_runs_outcome",
        ),
        sa.CheckConstraint(
            "duration_ms >= 0 AND duration_ms <= 180000",
            name="ck_scenario_runs_duration",
        ),
        sa.ForeignKeyConstraint(["scenario_id"], ["website_scenarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["journey_id"], ["website_journeys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scenario_runs_scenario_id_created_at",
        "scenario_runs",
        ["scenario_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scenario_runs_scenario_id_created_at", table_name="scenario_runs")
    op.drop_table("scenario_runs")
    op.drop_index("ix_website_scenarios_website_id_created_at", table_name="website_scenarios")
    op.drop_table("website_scenarios")
