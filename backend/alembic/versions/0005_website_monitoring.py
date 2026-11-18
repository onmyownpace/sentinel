"""Add monitoring_enabled to websites.

Revision ID: 0005_website_monitoring
Revises: 0004_analysis_provider
Create Date: 2026-11-15

Opt-in enrollment for n8n scheduled checks. Default is false so nothing is
checked on a timer until a person enables monitoring for that site.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_website_monitoring"
down_revision: Union[str, Sequence[str], None] = "0004_analysis_provider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "websites",
        sa.Column(
            "monitoring_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("websites", "monitoring_enabled")
