"""Package a trained model into the signed registry layout the service loads (FRD 13.2 + 11.1).
usage: python -m training.build_registry --onnx X.onnx --embeddings X.npz --pattern pattern.json --split split.csv --cache images_320
                                         --version 1.0.0 --out models --init-keys"""
from __future__ import annotations
import argparse, datetime, json, shutil
from pathlib import Path
import pandas as pd
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from preveda_dr.ml.registry import sha256_file, sign_record
from preveda_dr.ml.triage import load_guidelines
from training.evaluate import score_split, summarize
from training.settings import ROOT


def init_keys(private: Path, public: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    private.parent.mkdir(parents=True, exist_ok=True); public.parent.mkdir(parents=True, exist_ok=True)
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def main(argv=None) -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--onnx", required=True); a.add_argument("--embeddings", required=True); a.add_argument("--pattern", required=True)
    a.add_argument("--split", required=True); a.add_argument("--cache", required=True)
    a.add_argument("--version", default="1.0.0"); a.add_argument("--stage", default="STAGING")
    a.add_argument("--out", default=str(ROOT / "models")); a.add_argument("--guidelines", default=str(ROOT / "config" / "guidelines.json"))
    a.add_argument("--private-key", default=str(ROOT / "secrets" / "registry_private.pem")); a.add_argument("--init-keys", action="store_true")
    a = a.parse_args(argv)
    out, priv, pub = Path(a.out), Path(a.private_key), Path(a.out) / "keys" / "registry_public.pem"
    if a.init_keys and not priv.exists():
        init_keys(priv, pub); print("generated signing key pair (private key stays OUT of the container image)")
    pat = json.loads(Path(a.pattern).read_text())
    gl = load_guidelines(Path(a.guidelines))
    df = score_split(Path(a.onnx), pat["classes"], Path(a.split), Path(a.cache), pat["input"]["mean"], pat["input"]["std"])
    metrics = summarize(df, pat["classes"], gl["thresholds"])
    sp = pd.read_csv(a.split)
    vdir = out / "registry" / a.version
    vdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(a.onnx, vdir / "dr_model.onnx"); shutil.copy2(a.embeddings, vdir / "reference_embeddings.npz")
    record = {
        "model_name": "madhu-dr", "version": a.version, "stage": a.stage, "aggregation": "LOCAL_ONLY",
        "hospitals_n": 1, "patients_n": int(sp.patient.nunique()), "accuracy_metrics": metrics,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "architecture": pat["architecture"], "classes": pat["classes"], "input": pat["input"], "preprocessing": pat["preprocessing"],
        "low_confidence_below": pat["low_confidence_below"], "novelty": pat["novelty"],
        "training": {"images": int(len(sp)), "split_by": "patient", "n_train": int((sp.split == "train").sum()),
                     "n_val": int((sp.split == "val").sum()), "n_test": int((sp.split == "test").sum())},
        "artefact": {"file": "dr_model.onnx", "sha256": sha256_file(vdir / "dr_model.onnx"),
                     "embeddings_file": "reference_embeddings.npz", "path": f"registry/{a.version}/dr_model.onnx"},
    }
    record["signature"] = sign_record(record, priv.read_bytes())
    (vdir / "registry.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (out / "registry" / "CURRENT").write_text(a.version)
    print(json.dumps(metrics, indent=2)); print(f"registered madhu-dr {a.version} ({a.stage}) -> {vdir}")


if __name__ == "__main__":
    main()
