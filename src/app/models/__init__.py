from __future__ import annotations

from importlib import import_module


MODEL_MODULES = (
    "app.models.user",
    "app.models.tenant",
    "app.models.tenant_membership",
    "app.models.seller_profile",
    "app.models.icp_profile",
)


def load_model_modules() -> None:
    for module_name in MODEL_MODULES:
        import_module(module_name)


load_model_modules()

from app.models.icp_profile import ICPProfile
from app.models.seller_profile import SellerProfile
from app.models.tenant import Tenant
from app.models.tenant_membership import TenantMembership
from app.models.user import User

__all__ = [
    "ICPProfile",
    "SellerProfile",
    "Tenant",
    "TenantMembership",
    "User",
    "load_model_modules",
]
