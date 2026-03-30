from __future__ import annotations

from importlib import import_module


MODEL_MODULES = (
    "app.models.account",
    "app.models.account_research_snapshot",
    "app.models.approval_decision",
    "app.models.artifact",
    "app.models.contact",
    "app.models.conversation_message",
    "app.models.conversation_thread",
    "app.models.icp_profile",
    "app.models.run_event",
    "app.models.user",
    "app.models.tenant",
    "app.models.tenant_membership",
    "app.models.seller_profile",
    "app.models.source_evidence",
    "app.models.workflow_run",
)


def load_model_modules() -> None:
    for module_name in MODEL_MODULES:
        import_module(module_name)


load_model_modules()

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
from app.models.tenant import Tenant
from app.models.tenant_membership import TenantMembership
from app.models.user import User
from app.models.workflow_run import WorkflowRun

__all__ = [
    "Account",
    "AccountResearchSnapshot",
    "ApprovalDecision",
    "Artifact",
    "Contact",
    "ConversationMessage",
    "ConversationThread",
    "ICPProfile",
    "RunEvent",
    "SellerProfile",
    "SourceEvidence",
    "Tenant",
    "TenantMembership",
    "User",
    "WorkflowRun",
    "load_model_modules",
]
