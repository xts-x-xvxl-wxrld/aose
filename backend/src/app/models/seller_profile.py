from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin, status_check


if TYPE_CHECKING:
    from app.models.conversation_thread import ConversationThread
    from app.models.icp_profile import ICPProfile
    from app.models.tenant import Tenant
    from app.models.user import User


SELLER_SOURCE_STATUSES = ("manual", "imported", "generated")


class SellerProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "seller_profiles"
    __table_args__ = (
        status_check("source_status", SELLER_SOURCE_STATUSES, name="source_status_allowed"),
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    product_summary: Mapped[str] = mapped_column(Text, nullable=False)
    value_proposition: Mapped[str] = mapped_column(Text, nullable=False)
    target_market_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    profile_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="seller_profiles")
    created_by_user: Mapped["User"] = relationship(
        back_populates="created_seller_profiles",
        foreign_keys=[created_by_user_id],
    )
    updated_by_user: Mapped["User | None"] = relationship(
        back_populates="updated_seller_profiles",
        foreign_keys=[updated_by_user_id],
    )
    icp_profiles: Mapped[list["ICPProfile"]] = relationship(back_populates="seller_profile")
    conversation_threads: Mapped[list["ConversationThread"]] = relationship(back_populates="seller_profile")
