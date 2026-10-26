"""Model registry + integrity (FRD 13.2 Model Registry, 11.1 Model Integrity: ECDSA-256 signature on every model).
Layout:  models/registry/<version>/{dr_model.onnx, reference_embeddings.npz, registry.json}
         models/registry/CURRENT          (text file holding the active version)
         models/keys/registry_public.pem  (public key; the private key never ships with the node)"""
from __future__ import annotations
import base64, hashlib, json
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


class ModelIntegrityError(RuntimeError):
    """Raised when a model file or its registry record fails verification - the node must refuse to load it."""


def canonical(record: dict) -> bytes:
    body = {k: v for k, v in record.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_record(record: dict, private_pem: bytes) -> dict:
    key = serialization.load_pem_private_key(private_pem, password=None)
    sig = key.sign(canonical(record), ec.ECDSA(hashes.SHA256()))
    return {"alg": "ECDSA-P256-SHA256", "value": base64.b64encode(sig).decode()}


def verify_record(record: dict, public_pem: bytes) -> bool:
    sig = (record.get("signature") or {}).get("value")
    if not sig:
        return False
    try:
        pub = serialization.load_pem_public_key(public_pem)
        pub.verify(base64.b64decode(sig), canonical(record), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


@dataclass
class ModelBundle:
    version: str
    onnx_path: Path
    record: dict
    centroids: np.ndarray
    signature_verified: bool

    @property
    def classes(self) -> list[str]:
        return self.record["classes"]


def load_bundle(models_dir: Path, version: str | None = None, require_signature: bool = True) -> ModelBundle:
    reg = Path(models_dir) / "registry"
    if version is None:
        version = (reg / "CURRENT").read_text().strip()
    vdir = reg / version
    record = json.loads((vdir / "registry.json").read_text(encoding="utf-8"))
    onnx = vdir / record["artefact"]["file"]
    if sha256_file(onnx) != record["artefact"]["sha256"]:
        raise ModelIntegrityError(f"model file hash mismatch for version {version} - file was modified")
    pub = Path(models_dir) / "keys" / "registry_public.pem"
    verified = pub.exists() and verify_record(record, pub.read_bytes())
    if require_signature and not verified:
        raise ModelIntegrityError(f"registry record for version {version} is unsigned or the signature is invalid")
    emb = np.load(vdir / record["artefact"]["embeddings_file"])
    return ModelBundle(version, onnx, record, emb["centroids"].astype(np.float32), verified)
