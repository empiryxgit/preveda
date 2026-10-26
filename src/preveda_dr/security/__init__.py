"""Authentication (JWT / Keycloak) and role checks (FRD 9.1, 12)."""
from .auth import AUDIT_ROLES, PREDICT_ROLES, READ_ROLES, Principal, require

__all__ = ["AUDIT_ROLES", "PREDICT_ROLES", "READ_ROLES", "Principal", "require"]
from . import demo  # noqa: F401,E402
