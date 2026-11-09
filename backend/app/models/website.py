"""A website the prototype remembers.

There is no owner column. Milestone 2 is a single shared registry on one
development machine, not an account system.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base


class Website(Base):
    """One registered site, identified by a UUID."""

    __tablename__ = "websites"
    __table_args__ = (
        UniqueConstraint("base_url", name="uq_websites_base_url"),
        CheckConstraint(
            "base_url ~ '^https?://'",
            name="ck_websites_base_url_http",
        ),
        CheckConstraint(
            "char_length(btrim(name)) >= 1",
            name="ck_websites_name_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # passive_deletes leaves the DELETE to PostgreSQL. The foreign key uses
    # ON DELETE CASCADE, so the check rows go away with the website.
    checks: Mapped[list["WebsiteCheck"]] = relationship(
        back_populates="website",
        passive_deletes=True,
    )
