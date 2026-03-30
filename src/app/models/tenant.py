from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin, status_check


if TYPE_CHECKING:
    from app.models.icp_profile import ICPProfile
    from app.models.seller_profile import SellerProfile
    from app.models.tenant_membership import TenantMembership


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
