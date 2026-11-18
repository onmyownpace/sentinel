"""Users, sessions, and website ownership.

Revision ID: 0006_users_sessions_owner
Revises: 0005_website_monitoring
Create Date: 2026-11-15

Learning-scale accounts: email/password users, cookie sessions, and an
optional owner_id on websites. Existing websites keep a null owner until the
startup seed claims them for the development account.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_users_sessions_owner"
down_revision: Union[str, Sequence[str], None] = "0005_website_monitoring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    op.add_column("websites", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_index("ix_websites_owner_id", "websites", ["owner_id"])
    op.create_foreign_key(
        "fk_websites_owner_id_users",
        "websites",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_websites_owner_id_users", "websites", type_="foreignkey")
    op.drop_index("ix_websites_owner_id", table_name="websites")
    op.drop_column("websites", "owner_id")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
