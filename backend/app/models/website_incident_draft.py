"""AI-3 incident summary drafts (webhook-friendly JSON)."""

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.website import Website


class WebsiteIncidentDraft(Base):
    """One incident paragraph draft built from recent failed checks + analyses."""

    __tablename__ = "website_incident_drafts"
    __table_args__ = (
        CheckConstraint(
            "failed_check_limit >= 1 AND failed_check_limit <= 20",
            name="ck_website_incident_drafts_limit",
        ),
        CheckConstraint(
            "failed_check_count >= 1 AND failed_check_count <= failed_check_limit",
            name="ck_website_incident_drafts_count",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_website_incident_drafts_severity",
        ),
        CheckConstraint(
            "provider IN ('simulated', 'openai')",
            name="ck_website_incident_drafts_provider",
        ),
        CheckConstraint(
            "char_length(btrim(paragraph)) >= 1",
            name="ck_website_incident_drafts_paragraph_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(text)) >= 1",
            name="ck_website_incident_drafts_text_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(limitations)) >= 1",
            name="ck_website_incident_drafts_limitations_not_blank",
        ),
        Index(
            "ix_website_incident_drafts_website_id_created_at",
            "website_id",
            "created_at",
        ),
        Index(
            "ix_website_incident_drafts_website_fingerprint",
            "website_id",
            "source_fingerprint",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    website_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
    )
    failed_check_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_check_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    check_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    analysis_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    website_name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    paragraph: Mapped[str] = mapped_column(String(4000), nullable=False)
    # Slack/Discord-friendly one-liner (AUTO-1 draft shape).
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    observations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[str] = mapped_column(String(800), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="simulated")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    website: Mapped[Website] = relationship(back_populates="incident_drafts")
