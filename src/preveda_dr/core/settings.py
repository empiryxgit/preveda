"""All configuration comes from environment variables (12-factor), so one container image runs on any node."""
from __future__ import annotations
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # project root (/app inside the container)


@dataclass(frozen=True)
class Settings:
    models_dir: Path
    model_version: str | None        # None -> use models/registry/CURRENT
    database_url: str                # sqlite (offline fallback) or postgresql+psycopg://...
    hospital_node_id: str
    auth_mode: str                   # off | hs256 | jwks   (jwks = Keycloak)
    jwt_secret: str
    jwks_url: str
    jwt_audience: str | None
    require_signature: bool          # refuse unsigned / tampered models (FRD 11.1 Model Integrity)
    guidelines_path: Path
    max_upload_mb: int
    hash_salt: str                   # pseudonymisation salt for patient references
    store_thumbnails: bool
    ort_threads: int
    demo_login: bool = True          # dummy UI login; only honoured when auth_mode == off
    demo_users: str = ""
    images_dir: str = "/images"       # default folder to read images from (a mounted host folder in Docker)
    session_hours: int = 8
    api_port: int = 8080              # REST API listener inside the container
    web_port: int = 8081              # web app listener inside the container
    bind_host: str = "0.0.0.0"
    path_map: str = ""              # Windows drive -> mount point, e.g. "C:=/host/c,D:=/host/d"
    public_api_url: str = ""          # shown in the web app (the host-side URL of the API)


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


@lru_cache
def get_settings() -> Settings:
    e = os.environ.get
    return Settings(
        models_dir=Path(e("PREVEDA_MODELS_DIR", str(ROOT / "models"))),
        model_version=e("PREVEDA_MODEL_VERSION") or None,
        database_url=e("PREVEDA_DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'madhu_dr.db'}"),
        hospital_node_id=e("PREVEDA_HOSPITAL_NODE_ID", "NODE-DEV"),
        auth_mode=e("PREVEDA_AUTH_MODE", "off").lower(),
        jwt_secret=e("PREVEDA_JWT_SECRET", ""),
        jwks_url=e("PREVEDA_JWKS_URL", ""),
        jwt_audience=e("PREVEDA_JWT_AUDIENCE") or None,
        require_signature=_bool("PREVEDA_REQUIRE_SIGNATURE", "true"),
        guidelines_path=Path(e("PREVEDA_GUIDELINES", str(ROOT / "config" / "guidelines.json"))),
        max_upload_mb=int(e("PREVEDA_MAX_UPLOAD_MB", "15")),
        hash_salt=e("PREVEDA_PATIENT_HASH_SALT", "change-me-per-hospital"),
        store_thumbnails=_bool("PREVEDA_STORE_THUMBNAILS", "true"),
        ort_threads=int(e("PREVEDA_ORT_THREADS", "0")),
        demo_login=_bool("PREVEDA_DEMO_LOGIN", "true"),
        demo_users=e("PREVEDA_DEMO_USERS", "doctor:doctor123:clinician:Dr. Demo,admin:admin123:hospital_admin:Hospital Admin"),
        images_dir=e("PREVEDA_IMAGES_DIR", "/images"),
        session_hours=int(e("PREVEDA_SESSION_HOURS", "8")),
        api_port=int(e("PREVEDA_API_PORT", "8080")),
        web_port=int(e("PREVEDA_WEB_PORT", "8081")),
        bind_host=e("PREVEDA_BIND_HOST", "0.0.0.0"),
        path_map=e("PREVEDA_PATH_MAP", ""),
        public_api_url=e("PREVEDA_PUBLIC_API_URL", ""),
    )
