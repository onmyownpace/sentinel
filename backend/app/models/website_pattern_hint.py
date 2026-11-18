"""AI-2 historical pattern hints for one website (reuse-cached)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.website import Website


class WebsitePatternHint(Base):
    """On-demand historical pattern summary for one site's recent checks."""

    __tablename__ = "website_pattern_hints"
    __table_args__ = (
        UniqueConstraint("website_id", name="uq_website_pattern_hints_website_id"),
        CheckConstraint(
            '"window" IN (\'24h\', \'7d\', \'all\')',
            name="ck_website_pattern_hints_window",
        ),
        CheckConstraint(
            "sample_limit >= 1 AND sample_limit <= 200",
            name="ck_website_pattern_hints_sample_limit",
        ),
        CheckConstraint(
            "check_count >= 0 AND failure_count >= 0 AND failure_count <= check_count",
            name="ck_website_pattern_hints_counts",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_website_pattern_hints_severity",
        ),
        CheckConstraint(
            "provider IN ('simulated', 'openai')",
            name="ck_website_pattern_hints_provider",
        ),
        CheckConstraint(
            "char_length(btrim(summary)) >= 1",
            name="ck_website_pattern_hints_summary_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(limitations)) >= 1",
            name="ck_website_pattern_hints_limitations_not_blank",
        ),
        Index("ix_website_pattern_hints_website_id_created_at", "website_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    website_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
    )
    window: Mapped[str] = mapped_column(String(8), nullable=False)
    sample_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    check_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False)
    based_on_latest_check_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("website_checks.id", ondelete="SET NULL"),
        nullable=True,
    )
    summary: Mapped[str] = mapped_column(String(800), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    patterns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    confirmed_observations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    recommended_investigation_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[str] = mapped_column(String(800), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="simulated")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    website: Mapped[Website] = relationship(back_populates="pattern_hint")
