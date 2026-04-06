from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin, status_check


if TYPE_CHECKING:
    from app.models.seller_profile import SellerProfile
    from app.models.tenant import Tenant
    from app.models.user import User


ICP_PROFILE_STATUSES = ("draft", "active", "archived")


class ICPProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "icp_profiles"
    __table_args__ = (
        status_check("status", ICP_PROFILE_STATUSES, name="status_allowed"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    seller_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("seller_profiles.id", ondelete="RESTRICT"),
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default="draft")
    criteria_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    exclusions_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="icp_profiles")
    seller_profile: Mapped["SellerProfile"] = relationship(back_populates="icp_profiles")
    created_by_user: Mapped["User"] = relationship(
        back_populates="created_icp_profiles",
        foreign_keys=[created_by_user_id],
    )
    updated_by_user: Mapped["User | None"] = relationship(
        back_populates="updated_icp_profiles",
        foreign_keys=[updated_by_user_id],
    )
