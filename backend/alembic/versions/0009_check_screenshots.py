"""Optional local screenshot path on website_checks (BROW-1).

Revision ID: 0009_check_screenshots
Revises: 0008_website_notification_rules
Create Date: 2026-11-16

Stores a relative path under the configured screenshot directory. Null means
no artifact was captured or the capture was skipped/oversized.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_check_screenshots"
down_revision = "0008_website_notification_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "website_checks",
        sa.Column("screenshot_path", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("website_checks", "screenshot_path")
