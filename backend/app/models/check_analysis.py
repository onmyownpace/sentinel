"""Stored AI analysis for one failed website check.

One check has at most one analysis. That unique constraint is the cost control
for repeated paid provider calls. Deleting the check deletes this row.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base


class CheckFailureAnalysis(Base):
    """Structured failure analysis produced for one website check."""

    __tablename__ = "check_failure_analyses"
    __table_args__ = (
        UniqueConstraint("check_id", name="uq_check_failure_analyses_check_id"),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_check_failure_analyses_severity",
        ),
        CheckConstraint(
            "char_length(btrim(summary)) >= 1",
            name="ck_check_failure_analyses_summary_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(limitations)) >= 1",
            name="ck_check_failure_analyses_limitations_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(model_name)) >= 1",
            name="ck_check_failure_analyses_model_not_blank",
        ),
        CheckConstraint(
            "provider IN ('simulated', 'openai')",
            name="ck_check_failure_analyses_provider",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    check_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("website_checks.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(String(800), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confirmed_observations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    possible_causes: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    recommended_investigation_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[str] = mapped_column(String(800), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # `simulated` is local heuristics. `openai` is a live model call.
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="simulated")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    check: Mapped["WebsiteCheck"] = relationship(back_populates="failure_analysis")
