from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin, status_check
from app.orchestration.contracts import WORKFLOW_TYPES

if TYPE_CHECKING:
    from app.models.conversation_message import ConversationMessage
    from app.models.seller_profile import SellerProfile
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.workflow_run import WorkflowRun


CONVERSATION_THREAD_STATUSES = ("active", "closed")


class ConversationThread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_threads"
    __table_args__ = (
        status_check("status", CONVERSATION_THREAD_STATUSES, name="status_allowed"),
        status_check("active_workflow", WORKFLOW_TYPES, name="active_workflow_allowed"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    seller_profile_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("seller_profiles.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    active_workflow: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
    )
    current_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "workflow_runs.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_conversation_threads_current_run_id_workflow_runs",
        ),
        nullable=True,
    )
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="conversation_threads")
    created_by_user: Mapped[User] = relationship(
        back_populates="created_conversation_threads",
        foreign_keys=[created_by_user_id],
    )
    seller_profile: Mapped[SellerProfile | None] = relationship(
        back_populates="conversation_threads"
    )
    current_run: Mapped[WorkflowRun | None] = relationship(
        foreign_keys=[current_run_id],
        post_update=True,
        overlaps="thread,workflow_runs",
    )
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="thread",
        foreign_keys="WorkflowRun.thread_id",
        overlaps="current_run",
    )
    messages: Mapped[list[ConversationMessage]] = relationship(back_populates="thread")
