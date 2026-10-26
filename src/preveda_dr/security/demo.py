"""DUMMY login for the built-in web UI (trials and demos only).
Honoured only while PREVEDA_AUTH_MODE=off. For real use, switch to hs256/jwks (Keycloak) - this module then answers 404."""
from __future__ import annotations
import secrets, time
from dataclasses import dataclass
from fastapi import Header, HTTPException
from ..core.settings import get_settings


@dataclass
class Session:
    user: str
    name: str
    role: str
    exp: float


_SESSIONS: dict[str, Session] = {}
_FAILS: dict[str, list[float]] = {}
ADMIN_ROLES = ("hospital_admin",)
WORK_ROLES = ("clinician", "hospital_admin")


def enabled() -> bool:
    s = get_settings()
    return s.demo_login and s.auth_mode == "off"


def _users() -> dict:
    out = {}
    for part in get_settings().demo_users.split(","):
        b = [x.strip() for x in part.split(":")]
        if len(b) >= 3:
            out[b[0]] = (b[1], b[2], b[3] if len(b) > 3 else b[0])
    return out


def login(username: str, password: str) -> tuple[str, Session]:
    if not enabled():
        raise HTTPException(404, "demo login is disabled")
    now = time.time()
    fails = [t for t in _FAILS.get(username, []) if now - t < 300]
    if len(fails) >= 5:
        raise HTTPException(429, "too many attempts, wait a few minutes")
    u = _users().get(username)
    if not u or not secrets.compare_digest(u[0].encode(), password.encode()):
        _FAILS[username] = fails + [now]
        raise HTTPException(401, "wrong username or password")
    _FAILS.pop(username, None)
    tok = secrets.token_urlsafe(32)
    s = Session(username, u[2], u[1], now + get_settings().session_hours * 3600)
    _SESSIONS[tok] = s
    return tok, s


def _token(authorization: str | None) -> str | None:
    return authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None


def logout(authorization: str | None) -> None:
    _SESSIONS.pop(_token(authorization) or "", None)


def current(*roles: str):
    def dep(authorization: str | None = Header(None)) -> Session:
        if not enabled():
            raise HTTPException(404, "demo login is disabled")
        tok = _token(authorization)
        s = _SESSIONS.get(tok or "")
        if not s or s.exp < time.time():
            _SESSIONS.pop(tok or "", None)
            raise HTTPException(401, "please sign in")
        if roles and s.role not in roles:
            raise HTTPException(403, "your role cannot do this")
        return s
    return dep
