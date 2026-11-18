"""BROW-3 scenario library: named reusable entries that wrap BROW-2 journeys."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
    from app.models.website_journey import WebsiteJourney


class WebsiteScenario(Base):
    """Named library item on a website, backed by one journey's steps."""

    __tablename__ = "website_scenarios"
    __table_args__ = (
        UniqueConstraint("website_id", "name", name="uq_website_scenarios_website_name"),
        CheckConstraint(
            "char_length(btrim(name)) >= 1",
            name="ck_website_scenarios_name_not_blank",
        ),
        Index("ix_website_scenarios_website_id_created_at", "website_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    website_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
    )
    journey_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("website_journeys.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Reserved for later schedule enrollment. Not wired to n8n in BROW-3.
    schedule_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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

    website: Mapped[Website] = relationship(back_populates="scenarios")
    journey: Mapped[WebsiteJourney] = relationship(back_populates="scenarios")
    runs: Mapped[list[ScenarioRun]] = relationship(
        back_populates="scenario",
        passive_deletes=True,
    )


class ScenarioRun(Base):
    """One on-demand execution of a library scenario."""

    __tablename__ = "scenario_runs"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('success', 'failed')",
            name="ck_scenario_runs_outcome",
        ),
        CheckConstraint(
            "duration_ms >= 0 AND duration_ms <= 180000",
            name="ck_scenario_runs_duration",
        ),
        Index("ix_scenario_runs_scenario_id_created_at", "scenario_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("website_scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    website_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
    )
    journey_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("website_journeys.id", ondelete="CASCADE"),
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

    scenario: Mapped[WebsiteScenario] = relationship(back_populates="runs")
