"""JWT auth + RBAC (FRD 9.1, 12.1). Keycloak issues the tokens in production (jwks mode); hs256 is for local tests."""
from __future__ import annotations
from dataclasses import dataclass
import jwt
from fastapi import Header, HTTPException
from ..core.settings import get_settings

PREDICT_ROLES = ("clinician", "hospital_admin", "preveda_super_admin")
READ_ROLES = PREDICT_ROLES
AUDIT_ROLES = ("auditor", "hospital_admin", "preveda_super_admin")
_jwks_client = None


@dataclass
class Principal:
    user: str
    roles: set[str]


def _claims(token: str) -> dict:
    global _jwks_client
    s = get_settings()
    opts = {"verify_aud": s.jwt_audience is not None}
    if s.auth_mode == "hs256":
        return jwt.decode(token, s.jwt_secret, algorithms=["HS256"], audience=s.jwt_audience, options=opts)
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(s.jwks_url)
    key = _jwks_client.get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=["RS256", "ES256"], audience=s.jwt_audience, options=opts)


def require(*allowed: str):
    """FastAPI dependency: 401 without a valid JWT, 403 for a wrong role or a wrong X-Hospital-Node (AC-S4)."""
    def dep(authorization: str | None = Header(None), x_hospital_node: str | None = Header(None)) -> Principal:
        s = get_settings()
        if s.auth_mode == "off":
            return Principal("dev-user", {"preveda_super_admin"})
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "missing bearer token")
        try:
            c = _claims(authorization.split(" ", 1)[1])
        except jwt.PyJWTError:
            raise HTTPException(401, "invalid or expired token")
        roles = set((c.get("realm_access") or {}).get("roles") or c.get("roles") or [])
        if not roles & set(allowed):
            raise HTTPException(403, "role not permitted for this endpoint")
        if x_hospital_node != s.hospital_node_id:
            raise HTTPException(403, "X-Hospital-Node header missing or does not match this node")
        return Principal(c.get("preferred_username") or c.get("sub") or "unknown", roles)
    return dep
