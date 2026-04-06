from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from app.models.account_research_snapshot import AccountResearchSnapshot
    from app.models.contact import Contact
    from app.models.source_evidence import SourceEvidence
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.workflow_run import WorkflowRun


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index(
            "uq_accounts_tenant_normalized_domain",
            "tenant_id",
            "normalized_domain",
            unique=True,
            postgresql_where=text("normalized_domain IS NOT NULL"),
        ),
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
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_workflow_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    hq_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employee_range: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    fit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    fit_signals_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    canonical_data_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="accounts")
    created_by_user: Mapped["User"] = relationship(
        back_populates="created_accounts",
        foreign_keys=[created_by_user_id],
    )
    updated_by_user: Mapped["User | None"] = relationship(
        back_populates="updated_accounts",
        foreign_keys=[updated_by_user_id],
    )
    source_workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="accounts")
    research_snapshots: Mapped[list["AccountResearchSnapshot"]] = relationship(back_populates="account")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="account")
    source_evidence: Mapped[list["SourceEvidence"]] = relationship(back_populates="account")
