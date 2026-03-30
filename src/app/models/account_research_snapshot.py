from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.workflow_run import WorkflowRun


class AccountResearchSnapshot(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "account_research_snapshots"

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    research_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="account_research_snapshots")
    account: Mapped["Account"] = relationship(back_populates="research_snapshots")
    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="research_snapshots")
    created_by_user: Mapped["User"] = relationship(back_populates="created_account_research_snapshots")
