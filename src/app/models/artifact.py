from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin, status_check


if TYPE_CHECKING:
    from app.models.approval_decision import ApprovalDecision
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.workflow_run import WorkflowRun


ARTIFACT_TYPES = (
    "research_brief",
    "seller_summary",
    "icp_summary",
    "run_summary",
    "review_packet",
    "outreach_draft",
)
ARTIFACT_FORMATS = ("markdown", "json", "external_pointer")


class Artifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        status_check("artifact_type", ARTIFACT_TYPES, name="artifact_type_allowed"),
        status_check("format", ARTIFACT_FORMATS, name="format_allowed"),
        CheckConstraint(
            "("
            "(format = 'markdown' AND content_markdown IS NOT NULL) OR "
            "(format = 'json' AND content_json IS NOT NULL) OR "
            "(format = 'external_pointer' AND storage_url IS NOT NULL)"
            ")",
            name="format_content_consistency",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="artifacts")
    workflow_run: Mapped["WorkflowRun | None"] = relationship(back_populates="artifacts")
    created_by_user: Mapped["User | None"] = relationship(back_populates="created_artifacts")
    approval_decisions: Mapped[list["ApprovalDecision"]] = relationship(back_populates="artifact")
