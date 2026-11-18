"""Add provider column to check_failure_analyses.

Revision ID: 0004_analysis_provider
Revises: 0003_create_check_analyses
Create Date: 2026-11-14

Labels each stored analysis as simulated or openai so clients cannot mistake
local heuristics for a live model response.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_analysis_provider"
down_revision: Union[str, Sequence[str], None] = "0003_create_check_analyses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "check_failure_analyses",
        sa.Column(
            "provider",
            sa.String(length=16),
            nullable=False,
            server_default="simulated",
        ),
    )
    op.create_check_constraint(
        "ck_check_failure_analyses_provider",
        "check_failure_analyses",
        "provider IN ('simulated', 'openai')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_check_failure_analyses_provider",
        "check_failure_analyses",
        type_="check",
    )
    op.drop_column("check_failure_analyses", "provider")
