"""One browser check of a registered website.

Deleting the website deletes these rows. The foreign key uses
ON DELETE CASCADE, and `Website.checks` sets `passive_deletes` so
SQLAlchemy leaves that work to PostgreSQL.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base


class WebsiteCheck(Base):
    """The stored result of one bounded browser check."""

    __tablename__ = "website_checks"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('success', 'failed')",
            name="ck_website_checks_outcome",
        ),
        CheckConstraint(
            "duration_ms >= 0 AND duration_ms <= 120000",
            name="ck_website_checks_duration",
        ),
        CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="ck_website_checks_http_status",
        ),
        Index("ix_website_checks_website_id_created_at", "website_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    website_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    final_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    console_errors: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    failed_requests: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    website: Mapped["Website"] = relationship(back_populates="checks")
