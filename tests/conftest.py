import io, os, shutil, sys
from pathlib import Path
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def fundus_like(seed=0) -> bytes:
    """Synthetic stand-in for a retinal photo (orange disc on black) - enough to exercise the full pipeline."""
    im = Image.new("RGB", (900, 900), (0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((60, 60, 840, 840), fill=(200 - seed, 110, 40))
    d.ellipse((600, 380, 700, 480), fill=(240, 220, 150))
    b = io.BytesIO(); im.save(b, "JPEG"); return b.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    from preveda_dr.core.settings import get_settings
    monkeypatch.setenv("PREVEDA_MODELS_DIR", str(ROOT / "models"))
    monkeypatch.setenv("PREVEDA_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PREVEDA_GUIDELINES", str(ROOT / "config" / "guidelines.json"))
    monkeypatch.setenv("PREVEDA_HOSPITAL_NODE_ID", "NODE-TEST")
    monkeypatch.setenv("PREVEDA_AUTH_MODE", "off")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


@pytest.fixture
def client(env):
    from fastapi.testclient import TestClient
    from preveda_dr.api.main import create_app
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def models_copy(tmp_path):
    dst = tmp_path / "models"
    shutil.copytree(ROOT / "models", dst)
    return dst
