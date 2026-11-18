"""Create the check_failure_analyses table.

Revision ID: 0003_create_check_analyses
Revises: 0002_create_website_checks
Create Date: 2026-11-14

One analysis row per failed check. Deleting the check deletes the analysis.
The revision id stays within Alembic's 32-character version_num column.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_create_check_analyses"
down_revision: Union[str, Sequence[str], None] = "0002_create_website_checks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "check_failure_analyses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("check_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.String(length=800), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column(
            "confirmed_observations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "possible_causes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "recommended_investigation_steps",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("limitations", sa.String(length=800), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_check_failure_analyses_severity",
        ),
        sa.CheckConstraint(
            "char_length(btrim(summary)) >= 1",
            name="ck_check_failure_analyses_summary_not_blank",
        ),
        sa.CheckConstraint(
            "char_length(btrim(limitations)) >= 1",
            name="ck_check_failure_analyses_limitations_not_blank",
        ),
        sa.CheckConstraint(
            "char_length(btrim(model_name)) >= 1",
            name="ck_check_failure_analyses_model_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["check_id"],
            ["website_checks.id"],
            name="fk_check_failure_analyses_check_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("check_id", name="uq_check_failure_analyses_check_id"),
    )


def downgrade() -> None:
    op.drop_table("check_failure_analyses")
