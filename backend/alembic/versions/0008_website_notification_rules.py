"""Per-site AUTO-2 notification rule toggles.

Revision ID: 0008_website_notification_rules
Revises: 0007_website_thresholds
Create Date: 2026-11-16

Defaults are true so existing schedules keep notifying on fail / recover / latency
unless the operator turns a rule off.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_website_notification_rules"
down_revision = "0007_website_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "websites",
        sa.Column(
            "notify_on_fail",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "websites",
        sa.Column(
            "notify_on_recover",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "websites",
        sa.Column(
            "notify_on_latency",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("websites", "notify_on_latency")
    op.drop_column("websites", "notify_on_recover")
    op.drop_column("websites", "notify_on_fail")
