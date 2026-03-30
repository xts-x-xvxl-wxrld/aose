from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin, status_check


if TYPE_CHECKING:
    from app.models.conversation_thread import ConversationThread
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.workflow_run import WorkflowRun


CONVERSATION_MESSAGE_ROLES = ("user", "assistant", "system")
CONVERSATION_MESSAGE_TYPES = ("user_turn", "assistant_reply", "system_note", "workflow_status")


class ConversationMessage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        status_check("role", CONVERSATION_MESSAGE_ROLES, name="role_allowed"),
        status_check("message_type", CONVERSATION_MESSAGE_TYPES, name="message_type_allowed"),
        CheckConstraint(
            "message_type <> 'user_turn' OR created_by_user_id IS NOT NULL",
            name="user_turn_requires_creator",
        ),
        CheckConstraint(
            "message_type <> 'user_turn' OR run_id IS NULL",
            name="user_turn_run_id_null",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversation_threads.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="conversation_messages")
    thread: Mapped["ConversationThread"] = relationship(back_populates="messages")
    run: Mapped["WorkflowRun | None"] = relationship(back_populates="messages")
    created_by_user: Mapped["User | None"] = relationship(back_populates="created_conversation_messages")
