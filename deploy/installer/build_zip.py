"""Builds PreVeda-Madhu-DR-Installer.zip (Windows one-click installer) from this repository.
Usage:  python deploy/installer/build_zip.py [output_dir]
Never includes secrets/, tests/, data/ or caches."""
import os, shutil, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).parent / "windows"
out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent
IGNORE = shutil.ignore_patterns("secrets", "__pycache__", "*.pyc", ".pytest_cache", "data", "tests", ".env", ".git", "installer")
with tempfile.TemporaryDirectory() as tmp:
    pkg = Path(tmp) / "PreVeda-Madhu-DR"
    shutil.copytree(SRC, pkg)
    shutil.copytree(ROOT, pkg / "app", ignore=IGNORE)
    shutil.copy(ROOT / "LICENSE", pkg / "LICENSE.txt")
    out = out_dir / "PreVeda-Madhu-DR-Installer.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, fs in os.walk(pkg):
            for f in fs:
                p = Path(d) / f
                z.write(p, p.relative_to(pkg.parent))
    print(out, out.stat().st_size // 1024 // 1024, "MB")
