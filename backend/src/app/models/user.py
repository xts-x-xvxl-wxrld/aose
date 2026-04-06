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
    from app.models.seller_profile import SellerProfile
    from app.models.tenant_membership import TenantMembership
    from app.models.workflow_run import WorkflowRun


USER_STATUSES = ("active", "disabled")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        status_check("status", USER_STATUSES, name="status_allowed"),
    )

    external_auth_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_platform_admin: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")

    memberships: Mapped[list["TenantMembership"]] = relationship(back_populates="user")
    created_seller_profiles: Mapped[list["SellerProfile"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="SellerProfile.created_by_user_id",
    )
    updated_seller_profiles: Mapped[list["SellerProfile"]] = relationship(
        back_populates="updated_by_user",
        foreign_keys="SellerProfile.updated_by_user_id",
    )
    created_icp_profiles: Mapped[list["ICPProfile"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="ICPProfile.created_by_user_id",
    )
    updated_icp_profiles: Mapped[list["ICPProfile"]] = relationship(
        back_populates="updated_by_user",
        foreign_keys="ICPProfile.updated_by_user_id",
    )
    created_conversation_threads: Mapped[list["ConversationThread"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="ConversationThread.created_by_user_id",
    )
    created_conversation_messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="ConversationMessage.created_by_user_id",
    )
    created_workflow_runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="WorkflowRun.created_by_user_id",
    )
    created_accounts: Mapped[list["Account"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="Account.created_by_user_id",
    )
    updated_accounts: Mapped[list["Account"]] = relationship(
        back_populates="updated_by_user",
        foreign_keys="Account.updated_by_user_id",
    )
    created_account_research_snapshots: Mapped[list["AccountResearchSnapshot"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="AccountResearchSnapshot.created_by_user_id",
    )
    created_contacts: Mapped[list["Contact"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="Contact.created_by_user_id",
    )
    updated_contacts: Mapped[list["Contact"]] = relationship(
        back_populates="updated_by_user",
        foreign_keys="Contact.updated_by_user_id",
    )
    created_artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="Artifact.created_by_user_id",
    )
    reviewed_approval_decisions: Mapped[list["ApprovalDecision"]] = relationship(
        back_populates="reviewed_by_user",
        foreign_keys="ApprovalDecision.reviewed_by_user_id",
    )
