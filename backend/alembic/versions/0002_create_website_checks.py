"""Create the website_checks table.

Revision ID: 0002_create_website_checks
Revises: 0001_create_websites
Create Date: 2026-11-07

Deleting a website deletes its checks. The foreign key is ON DELETE CASCADE.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_create_website_checks"
down_revision: Union[str, Sequence[str], None] = "0001_create_websites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "website_checks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("website_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("page_title", sa.String(length=300), nullable=True),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "console_errors",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "failed_requests",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'failed')",
            name="ck_website_checks_outcome",
        ),
        sa.CheckConstraint(
            "duration_ms >= 0 AND duration_ms <= 120000",
            name="ck_website_checks_duration",
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="ck_website_checks_http_status",
        ),
        sa.ForeignKeyConstraint(
            ["website_id"],
            ["websites.id"],
            name="fk_website_checks_website_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_website_checks_website_id_created_at",
        "website_checks",
        ["website_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_website_checks_website_id_created_at", table_name="website_checks")
    op.drop_table("website_checks")
