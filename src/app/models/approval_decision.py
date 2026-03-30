from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin, status_check


if TYPE_CHECKING:
    from app.models.artifact import Artifact
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.workflow_run import WorkflowRun


APPROVAL_DECISIONS = ("approved", "rejected", "needs_changes")


class ApprovalDecision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        status_check("decision", APPROVAL_DECISIONS, name="decision_allowed"),
        CheckConstraint(
            "decision = 'approved' OR rationale IS NOT NULL",
            name="decision_requires_rationale",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    artifact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="approval_decisions")
    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="approval_decisions")
    artifact: Mapped["Artifact | None"] = relationship(back_populates="approval_decisions")
    reviewed_by_user: Mapped["User"] = relationship(back_populates="reviewed_approval_decisions")
