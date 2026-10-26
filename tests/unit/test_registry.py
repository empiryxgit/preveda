import json
import pytest
from preveda_dr.ml.registry import ModelIntegrityError, load_bundle


def test_signed_model_loads(models_copy):
    b = load_bundle(models_copy)
    assert b.signature_verified and b.version == "1.0.0" and b.classes == ["Ungradable", "Healthy", "DR", "Other"]


def test_modified_model_file_is_rejected(models_copy):     # AC-FL4: tampered model must be refused
    with open(models_copy / "registry" / "1.0.0" / "dr_model.onnx", "ab") as f:
        f.write(b"x")
    with pytest.raises(ModelIntegrityError, match="hash mismatch"):
        load_bundle(models_copy)


def test_edited_metrics_break_signature(models_copy):
    p = models_copy / "registry" / "1.0.0" / "registry.json"
    rec = json.loads(p.read_text()); rec["accuracy_metrics"]["auroc"] = 0.99
    p.write_text(json.dumps(rec))
    with pytest.raises(ModelIntegrityError, match="signature"):
        load_bundle(models_copy)
    assert load_bundle(models_copy, require_signature=False).signature_verified is False
