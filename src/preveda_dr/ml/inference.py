"""ONNX inference (FRD 4.3: all models run locally as ONNX files, no cloud calls)."""
from __future__ import annotations
import io
import numpy as np
import onnxruntime as ort
from PIL import Image, UnidentifiedImageError
from .preprocessing import preprocess_image, to_tensor_array
from .registry import ModelBundle
from .triage import assess


class InvalidImage(ValueError):
    pass


class Predictor:
    def __init__(self, bundle: ModelBundle, guidelines: dict, ort_threads: int = 0):
        so = ort.SessionOptions()
        if ort_threads > 0:
            so.intra_op_num_threads = ort_threads
        self.sess = ort.InferenceSession(str(bundle.onnx_path), so, providers=["CPUExecutionProvider"])
        r = bundle.record
        self.bundle, self.guidelines = bundle, guidelines
        self.classes = r["classes"]
        self.size = int(r["input"]["shape"][-1])
        self.mean, self.std = r["input"]["mean"], r["input"]["std"]
        self.low_conf = float(r["low_confidence_below"])
        self.novelty = r["novelty"]["threshold_per_class"]

    @staticmethod
    def open_image(data: bytes) -> Image.Image:
        try:
            Image.open(io.BytesIO(data)).verify()
            return Image.open(io.BytesIO(data))
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
            raise InvalidImage("file is not a readable image") from e

    def predict_pil(self, im: Image.Image) -> tuple[dict, Image.Image]:
        pre = preprocess_image(im, self.size)
        x = to_tensor_array(pre, self.mean, self.std)[None].astype(np.float32)
        logits, emb = self.sess.run(None, {"image": x})
        z = logits[0] - logits[0].max()
        p = np.exp(z) / np.exp(z).sum()
        e = emb[0] / np.linalg.norm(emb[0])
        k = int(p.argmax()); name = self.classes[k]
        dist = float(1.0 - e @ self.bundle.centroids[k])
        flags = []
        if p[k] < self.low_conf:
            flags.append("low_confidence")
        if dist > self.novelty[name]:
            flags.append("unlike_training_data")
        probs = {c: float(v) for c, v in zip(self.classes, p)}
        res = {"prediction": name, "confidence": float(p[k]), "probabilities": probs,
               "novelty_distance": dist, "flags": flags}
        res.update(assess(probs, name, flags, self.guidelines))
        return res, pre

    def predict_bytes(self, data: bytes) -> tuple[dict, Image.Image]:
        return self.predict_pil(self.open_image(data))
