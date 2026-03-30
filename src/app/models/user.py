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


USER_STATUSES = ("active", "disabled")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        status_check("status", USER_STATUSES, name="status_allowed"),
    )

    external_auth_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
