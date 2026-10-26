"""Image preprocessing. MUST stay identical to what the model was trained with (same crop, pad, resize, normalise)."""
from __future__ import annotations
import numpy as np
from PIL import Image

CROP_THRESHOLD = 12      # pixel value at/below this = black border around the retina circle


def preprocess_image(im: Image.Image, size: int) -> Image.Image:
    """RGB -> crop black border -> pad to square -> resize (bilinear)."""
    im = im.convert("RGB")
    a = np.asarray(im)
    mask = a.max(axis=2) > CROP_THRESHOLD
    if mask.any():
        ys, xs = np.where(mask)
        im = im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    w, h = im.size
    s = max(w, h)
    canvas = Image.new("RGB", (s, s), (0, 0, 0))
    canvas.paste(im, ((s - w) // 2, (s - h) // 2))
    return canvas.resize((size, size), Image.BILINEAR)


def to_tensor_array(im: Image.Image, mean, std) -> np.ndarray:
    """PIL image -> float32 (3, H, W), scaled to 0-1 and normalised."""
    a = np.asarray(im, dtype=np.float32) / 255.0
    a = (a - np.array(mean, dtype=np.float32)) / np.array(std, dtype=np.float32)
    return a.transpose(2, 0, 1)
