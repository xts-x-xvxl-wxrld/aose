from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin, status_check


if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.account_research_snapshot import AccountResearchSnapshot
    from app.models.approval_decision import ApprovalDecision
    from app.models.artifact import Artifact
    from app.models.conversation_message import ConversationMessage
    from app.models.conversation_thread import ConversationThread
    from app.models.run_event import RunEvent
    from app.models.source_evidence import SourceEvidence
    from app.models.tenant import Tenant
    from app.models.user import User


WORKFLOW_TYPES = (
    "seller_profile_setup",
    "icp_profile_setup",
    "account_search",
    "account_research",
    "contact_search",
)
WORKFLOW_RUN_STATUSES = ("queued", "running", "awaiting_review", "succeeded", "failed", "cancelled")


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        status_check("workflow_type", WORKFLOW_TYPES, name="workflow_type_allowed"),
        status_check("status", WORKFLOW_RUN_STATUSES, name="status_allowed"),
        Index(
            "uq_workflow_runs_tenant_correlation_id",
            "tenant_id",
            "correlation_id",
            unique=True,
            postgresql_where=text("correlation_id IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversation_threads.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="workflow_runs")
    thread: Mapped["ConversationThread | None"] = relationship(
        back_populates="workflow_runs",
        foreign_keys=[thread_id],
        overlaps="current_run",
    )
    created_by_user: Mapped["User"] = relationship(back_populates="created_workflow_runs")
    messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="run")
    run_events: Mapped[list["RunEvent"]] = relationship(back_populates="workflow_run")
    accounts: Mapped[list["Account"]] = relationship(back_populates="source_workflow_run")
    research_snapshots: Mapped[list["AccountResearchSnapshot"]] = relationship(back_populates="workflow_run")
    source_evidence: Mapped[list["SourceEvidence"]] = relationship(back_populates="workflow_run")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="workflow_run")
    approval_decisions: Mapped[list["ApprovalDecision"]] = relationship(back_populates="workflow_run")
