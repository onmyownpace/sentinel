"""Optional per-website latency and failure thresholds.

Revision ID: 0007_website_thresholds
Revises: 0006_users_sessions_owner
Create Date: 2026-11-16

Null means the threshold is unset. failure_threshold_count is how many newest
consecutive failed checks count as still_failing (default 1 when null at read).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_website_thresholds"
down_revision: Union[str, Sequence[str], None] = "0006_users_sessions_owner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "websites",
        sa.Column("latency_threshold_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "websites",
        sa.Column("failure_threshold_count", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_websites_latency_threshold_ms",
        "websites",
        "latency_threshold_ms IS NULL OR (latency_threshold_ms >= 1 AND latency_threshold_ms <= 120000)",
    )
    op.create_check_constraint(
        "ck_websites_failure_threshold_count",
        "websites",
        "failure_threshold_count IS NULL OR (failure_threshold_count >= 1 AND failure_threshold_count <= 20)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_websites_failure_threshold_count", "websites", type_="check")
    op.drop_constraint("ck_websites_latency_threshold_ms", "websites", type_="check")
    op.drop_column("websites", "failure_threshold_count")
    op.drop_column("websites", "latency_threshold_ms")
