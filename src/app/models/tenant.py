from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin, status_check


if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.account_research_snapshot import AccountResearchSnapshot
    from app.models.approval_decision import ApprovalDecision
    from app.models.artifact import Artifact
    from app.models.contact import Contact
    from app.models.conversation_message import ConversationMessage
    from app.models.conversation_thread import ConversationThread
    from app.models.icp_profile import ICPProfile
    from app.models.run_event import RunEvent
    from app.models.seller_profile import SellerProfile
    from app.models.source_evidence import SourceEvidence
    from app.models.tenant_membership import TenantMembership
    from app.models.workflow_run import WorkflowRun


TENANT_STATUSES = ("active", "suspended")


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        status_check("status", TENANT_STATUSES, name="status_allowed"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")

    memberships: Mapped[list["TenantMembership"]] = relationship(back_populates="tenant")
    seller_profiles: Mapped[list["SellerProfile"]] = relationship(back_populates="tenant")
    icp_profiles: Mapped[list["ICPProfile"]] = relationship(back_populates="tenant")
    conversation_threads: Mapped[list["ConversationThread"]] = relationship(back_populates="tenant")
    conversation_messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="tenant")
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="tenant")
    run_events: Mapped[list["RunEvent"]] = relationship(back_populates="tenant")
    accounts: Mapped[list["Account"]] = relationship(back_populates="tenant")
    account_research_snapshots: Mapped[list["AccountResearchSnapshot"]] = relationship(back_populates="tenant")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="tenant")
    source_evidence: Mapped[list["SourceEvidence"]] = relationship(back_populates="tenant")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="tenant")
    approval_decisions: Mapped[list["ApprovalDecision"]] = relationship(back_populates="tenant")
