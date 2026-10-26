"""Folder ingestion: the model runs inside the hospital and reads images from a configured folder.
Already-seen images are skipped by SHA-256, so a folder can be re-scanned safely."""
from __future__ import annotations
import hashlib, io, os, re, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from ..core.logging import log_event
from ..core.paths import to_server_path
from ..core.settings import get_settings
from ..ml.inference import InvalidImage

EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
MAX_FILES = 20000


def config(store) -> dict:
    s, m = get_settings(), store.settings_map()
    interval = int(m.get("scan_interval", 60) or 60)
    return {"watch_path": m.get("watch_path", s.images_dir), "auto_scan": m.get("auto_scan", "false") == "true",
            "scan_interval": max(10, min(interval, 86400))}


def validate_path(path: str) -> dict:
    out = {"path": path, "resolved": None, "exists": False, "is_dir": False, "readable": False, "image_count": 0, "sample": [], "message": ""}
    if not path or not path.strip():
        out["message"] = "Enter a folder path."
        return out
    real, msg = to_server_path(path)
    if real is None:
        out["message"] = msg
        return out
    out["resolved"], path = real, real
    p = Path(path.strip())
    out["exists"], out["is_dir"] = p.exists(), p.is_dir()
    if not out["exists"]:
        out["message"] = "Folder not found. Check the spelling, and that the drive is shared with Madhu-DR."
        return out
    if not out["is_dir"]:
        out["message"] = "That path is a file, not a folder."
        return out
    out["readable"] = os.access(p, os.R_OK | os.X_OK)
    if not out["readable"]:
        out["message"] = "The folder exists but the service has no permission to read it."
        return out
    n, sample = 0, []
    for root, _, files in os.walk(p):
        for f in files:
            if Path(f).suffix.lower() in EXT:
                n += 1
                if len(sample) < 5:
                    sample.append(os.path.relpath(os.path.join(root, f), p))
        if n >= MAX_FILES:
            break
    out["image_count"], out["sample"] = n, sample
    out["message"] = f"OK: found {n} image file(s)." if n else "Folder is readable but has no image files (jpg, png, tif, bmp)."
    return out


class FolderScanner:
    def __init__(self, app):
        self.app, self.lock = app, threading.Lock()
        self._stop = threading.Event()
        self.state = {"running": False, "total": 0, "done": 0, "new": 0, "skipped": 0, "failed": 0,
                      "errors": [], "started_at": None, "finished_at": None, "trigger": None, "message": ""}
        self._last_end = 0.0

    def status(self) -> dict:
        with self.lock:
            return dict(self.state, errors=list(self.state["errors"]))

    def start(self, actor: str) -> bool:
        with self.lock:
            if self.state["running"]:
                return False
            self.state.update(running=True, total=0, done=0, new=0, skipped=0, failed=0, errors=[], message="Starting...",
                              started_at=datetime.now(timezone.utc).isoformat(), finished_at=None, trigger=actor)
        threading.Thread(target=self._run, args=(actor,), daemon=True).start()
        return True

    def start_auto_loop(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(5):
            try:
                cfg = config(self.app.state.store)
                if cfg["auto_scan"] and not self.state["running"] and time.time() - self._last_end >= cfg["scan_interval"]:
                    self.start("auto-scan")
            except Exception as e:  # keep the loop alive
                log_event("auto-scan loop error", error=str(e))

    def _fail(self, msg: str) -> None:
        with self.lock:
            self.state.update(running=False, message=msg, finished_at=datetime.now(timezone.utc).isoformat())
        self._last_end = time.time()

    def _run(self, actor: str) -> None:
        st, s = self.app.state, get_settings()
        pred, store = st.predictor, st.store
        if pred is None:
            return self._fail(f"Model not available: {st.model_error}")
        cfg = config(store)
        v = validate_path(cfg["watch_path"])
        if not v["image_count"]:
            return self._fail(v["message"])
        root, files = Path(to_server_path(cfg["watch_path"])[0]), []
        for r, _, fs in os.walk(root):
            files += [os.path.join(r, f) for f in fs if Path(f).suffix.lower() in EXT]
            if len(files) >= MAX_FILES:
                break
        files.sort()
        with self.lock:
            self.state.update(total=len(files), message="Reading images...")
        bundle, limit = pred.bundle, s.max_upload_mb * 1024 * 1024
        for path in files:
            rel = os.path.relpath(path, root)
            try:
                if os.path.getsize(path) > limit:
                    raise InvalidImage("file larger than the upload limit")
                data = Path(path).read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                if store.has_image(sha):
                    with self.lock:
                        self.state["skipped"] += 1
                else:
                    t0 = time.perf_counter()
                    res, pre = pred.predict_bytes(data)
                    stem = Path(path).stem
                    eye = {"LE": "Left", "RE": "Right"}.get((re.search(r"(?:^|_)(LE|RE)(?:_|$)", stem) or [None, None])[1], "Unknown")
                    thumb = None
                    if s.store_thumbnails:
                        b = io.BytesIO(); pre.resize((300, 300)).save(b, "JPEG", quality=85); thumb = b.getvalue()
                    store.insert_result(dict(
                        result_id=str(uuid.uuid4()), hospital_node_id=s.hospital_node_id,
                        patient_hash=hashlib.sha256((s.hash_salt + stem).encode()).hexdigest(), eye=eye, image_sha256=sha,
                        model_version=bundle.version, model_stage=bundle.record.get("stage"), prediction=res["prediction"],
                        confidence=res["confidence"], probabilities=res["probabilities"], flags=res["flags"], triage=res["triage"],
                        ai_finding=res["ai_finding"], rationale=res["why"],
                        clinical_context={"source": "folder", "source_file": rel, "combined_id": stem},
                        thumbnail=thumb, latency_ms=(time.perf_counter() - t0) * 1000), actor=actor)
                    from ..monitoring.metrics import PREDICTIONS
                    PREDICTIONS.labels(res["triage"], bundle.version).inc()
                    with self.lock:
                        self.state["new"] += 1
            except Exception as e:
                with self.lock:
                    self.state["failed"] += 1
                    if len(self.state["errors"]) < 20:
                        self.state["errors"].append(f"{rel}: {e}")
            with self.lock:
                self.state["done"] += 1
        n = self.state
        self._fail(f"Finished: {n['new']} new, {n['skipped']} already scored, {n['failed']} failed.")
        log_event("folder scan finished", new=n["new"], skipped=n["skipped"], failed=n["failed"], trigger=actor)
