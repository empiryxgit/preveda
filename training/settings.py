"""Training-side settings. Paths come from env vars so the same code runs on a laptop or in the container."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("PREVEDA_DATA_DIR", ROOT.parent))          # folder holding the CSV, xlsx and 'Annotated Images'
IMG_DIR = DATA / "Annotated Images"
CSV_FILE = DATA / "Annotatation file.csv"
META_FILE = DATA / "metadata.xlsx"
WORK = Path(os.environ.get("PREVEDA_WORK_DIR", ROOT / "data" / "training"))   # labels, cached images, split, metrics
MODEL = Path(os.environ.get("PREVEDA_TRAIN_MODEL_DIR", WORK / "model"))        # raw training output before registration
CACHE = WORK / "images_320"

IMG_SIZE = 320
CLASSES = ["Ungradable", "Healthy", "DR", "Other"]
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
SEED = 42
TRAIN_MODE = os.environ.get("TRAIN_MODE", "finetune")    # finetune | fast
EPOCHS = int(os.environ.get("EPOCHS", "20"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "8"))
