from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin, status_check
from app.orchestration.contracts import RUN_EVENT_NAMES

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.workflow_run import WorkflowRun


class RunEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "run_events"
    __table_args__ = (
        status_check("event_name", RUN_EVENT_NAMES, name="event_name_allowed"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    tenant: Mapped[Tenant] = relationship(back_populates="run_events")
    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="run_events")
