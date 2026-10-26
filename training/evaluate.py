"""Score the held-out images with the ONNX model and compute the metrics the FRD registry stores (13.2): auroc, sensitivity, specificity, f1."""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
import onnxruntime as ort
from PIL import Image
from preveda_dr.ml.preprocessing import to_tensor_array


def score_split(onnx: Path, classes, split_csv: Path, cache: Path, mean, std, splits=("val", "test")) -> pd.DataFrame:
    sp = pd.read_csv(split_csv)
    sp = sp[sp.split.isin(splits)].reset_index(drop=True)
    sess = ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"])
    out = []
    for i in range(0, len(sp), 16):
        ch = sp.iloc[i:i + 16]
        x = np.stack([to_tensor_array(Image.open(cache / f).convert("RGB"), mean, std) for f in ch.disk_filename]).astype(np.float32)
        lg, _ = sess.run(None, {"image": x})
        p = np.exp(lg - lg.max(1, keepdims=True)); p /= p.sum(1, keepdims=True)
        for (_, r), q in zip(ch.iterrows(), p):
            out.append({"file": r.disk_filename, "split": r.split, "true": r.diagnosis, **{f"p_{c}": float(v) for c, v in zip(classes, q)}})
    return pd.DataFrame(out)


def auroc(score: np.ndarray, y: np.ndarray) -> float:
    pos, neg = score[y], score[~y]
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def _op(p, y, thr):
    f = p >= thr
    return float((f & y).sum() / max(y.sum(), 1)), float((~f & ~y).sum() / max((~y).sum(), 1))


def summarize(df: pd.DataFrame, classes, th: dict) -> dict:
    t, v = df[df.split == "test"], df[df.split == "val"]
    y = (t.true == "DR").values
    sens, spec = _op(t.p_DR.values, y, th["dr_review"])
    sens_h, spec_h = _op(t.p_DR.values, y, th["dr_high"])
    pred = t[[f"p_{c}" for c in classes]].values.argmax(1)
    truth = t.true.map({c: i for i, c in enumerate(classes)}).values
    f1s = []
    for k in range(len(classes)):
        tp = ((pred == k) & (truth == k)).sum(); fp = ((pred == k) & (truth != k)).sum(); fn = ((pred != k) & (truth == k)).sum()
        f1s.append(2 * tp / max(2 * tp + fp + fn, 1))
    yv = (v.true == "DR").values
    return {"auroc": round(auroc(t.p_DR.values, y), 4), "auroc_val": round(auroc(v.p_DR.values, yv), 4) if yv.any() else None,
            "sensitivity": round(sens, 4), "specificity": round(spec, 4), "threshold_review": th["dr_review"],
            "sensitivity_high": round(sens_h, 4), "specificity_high": round(spec_h, 4), "threshold_high": th["dr_high"],
            "f1_macro": round(float(np.mean(f1s)), 4), "accuracy": round(float((pred == truth).mean()), 4),
            "n_test": int(len(t)), "dr_test_images": int(y.sum()), "fairness_gap": None}
