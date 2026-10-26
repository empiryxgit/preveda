"""Image preprocessing used by BOTH training and prediction, so they always agree.
Only needs numpy + Pillow (no torch), so prediction works on a light install."""
import re
import numpy as np
from PIL import Image
from training.settings import IMG_SIZE, MEAN, STD

CROP_THRESHOLD = 12  # pixel value below this counts as the black border around the fundus circle


def image_key(filename: str) -> str:
    """Disk name '70001_LE_REM-1234_1657175861...jpg' and CSV name 'REM-1234_1657175861...jpg'
    share the part 'REM-xxxx_<timestamp>'. That part is the join key."""
    m = re.search(r"(REM-\d+_\d+)", filename)
    return m.group(1) if m else filename


def patient_id(filename: str) -> str:
    """Leading number of the disk file name is the patient (both eyes share it)."""
    return filename.split("_")[0]


def preprocess_image(path) -> Image.Image:
    """1) open as RGB  2) crop the black border  3) pad to a square  4) resize to IMG_SIZE."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im)
    mask = a.max(axis=2) > CROP_THRESHOLD
    if mask.any():
        ys, xs = np.where(mask)
        im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    w, h = im.size
    s = max(w, h)
    canvas = Image.new("RGB", (s, s), (0, 0, 0))
    canvas.paste(im, ((s - w) // 2, (s - h) // 2))
    return canvas.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)


def to_tensor_array(im: Image.Image) -> np.ndarray:
    """PIL image -> float32 array shaped (3, H, W), ImageNet-normalised."""
    a = np.asarray(im, dtype=np.float32) / 255.0
    a = (a - np.array(MEAN, dtype=np.float32)) / np.array(STD, dtype=np.float32)
    return a.transpose(2, 0, 1)
