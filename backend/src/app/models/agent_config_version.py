from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin, status_check


AGENT_CONFIG_SCOPE_TYPES = ("global", "tenant")
AGENT_CONFIG_STATUSES = ("draft", "active", "archived")


class AgentConfigVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_config_versions"
    __table_args__ = (
        status_check("scope_type", AGENT_CONFIG_SCOPE_TYPES, name="scope_type_allowed"),
        status_check("status", AGENT_CONFIG_STATUSES, name="status_allowed"),
        Index(
            "uq_agent_config_scope_agent_version",
            "scope_type",
            "tenant_id",
            "agent_name",
            "version",
            unique=True,
        ),
    )

    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default="draft")
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    feature_flags_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)
