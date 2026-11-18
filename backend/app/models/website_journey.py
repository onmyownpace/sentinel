"""Declarative mini-journeys (BROW-2), separate from one-shot website_checks."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, CheckConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.website import Website
    from app.models.website_scenario import WebsiteScenario


class WebsiteJourney(Base):
    """A named step list attached to one website."""

    __tablename__ = "website_journeys"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(name)) >= 1",
            name="ck_website_journeys_name_not_blank",
        ),
        Index("ix_website_journeys_website_id_created_at", "website_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    website_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
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

    website: Mapped[Website] = relationship(back_populates="journeys")
    runs: Mapped[list[JourneyRun]] = relationship(
        back_populates="journey",
        passive_deletes=True,
    )
    scenarios: Mapped[list[WebsiteScenario]] = relationship(
        back_populates="journey",
        passive_deletes=True,
    )


class JourneyRun(Base):
    """One execution of a journey (not a website_checks row)."""

    __tablename__ = "journey_runs"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('success', 'failed')",
            name="ck_journey_runs_outcome",
        ),
        CheckConstraint(
            "duration_ms >= 0 AND duration_ms <= 180000",
            name="ck_journey_runs_duration",
        ),
        Index("ix_journey_runs_journey_id_created_at", "journey_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    journey_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("website_journeys.id", ondelete="CASCADE"),
        nullable=False,
    )
    website_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    step_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    final_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    journey: Mapped[WebsiteJourney] = relationship(back_populates="runs")
