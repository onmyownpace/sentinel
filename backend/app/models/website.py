"""A website the prototype remembers.

`owner_id` links a site to the account that registered it. Rows created before
accounts, or created by automation, may have a null owner and stay visible to
any signed-in user on this learning machine.

Optional `latency_threshold_ms` and `failure_threshold_count` drive MON-2
monitoring state (still failing vs recovered) without Redis.

AUTO-2 notification toggles (`notify_on_fail` / `notify_on_recover` /
`notify_on_latency`) gate which drafts n8n may deliver after a check.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.website_incident_draft import WebsiteIncidentDraft
    from app.models.website_journey import WebsiteJourney
    from app.models.website_pattern_hint import WebsitePatternHint
    from app.models.website_scenario import WebsiteScenario


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
        CheckConstraint(
            "latency_threshold_ms IS NULL OR (latency_threshold_ms >= 1 AND latency_threshold_ms <= 120000)",
            name="ck_websites_latency_threshold_ms",
        ),
        CheckConstraint(
            "failure_threshold_count IS NULL OR (failure_threshold_count >= 1 AND failure_threshold_count <= 20)",
            name="ck_websites_failure_threshold_count",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Opt-in for n8n scheduled checks. False means the schedule skips this site.
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Optional max duration for a successful check. Null = ignore latency.
    latency_threshold_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Optional consecutive-failure count. Null means "1" at evaluation time.
    failure_threshold_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # AUTO-2: which monitoring signals may produce a webhook draft.
    notify_on_fail: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_recover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_latency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
    owner: Mapped[User | None] = relationship(back_populates="websites")
    # passive_deletes leaves the DELETE to PostgreSQL. The foreign key uses
    # ON DELETE CASCADE, so the check rows go away with the website.
    checks: Mapped[list["WebsiteCheck"]] = relationship(
        back_populates="website",
        passive_deletes=True,
    )
    journeys: Mapped[list["WebsiteJourney"]] = relationship(
        back_populates="website",
        passive_deletes=True,
    )
    scenarios: Mapped[list["WebsiteScenario"]] = relationship(
        back_populates="website",
        passive_deletes=True,
    )
    pattern_hint: Mapped["WebsitePatternHint | None"] = relationship(
        back_populates="website",
        uselist=False,
        passive_deletes=True,
    )
    incident_drafts: Mapped[list["WebsiteIncidentDraft"]] = relationship(
        back_populates="website",
        passive_deletes=True,
    )
