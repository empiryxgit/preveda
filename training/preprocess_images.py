"""STEP 2 - Turn the 2866x2866 camera images into small, uniform training images.
Reads : work/labels.csv + Annotated Images/
Writes: work/images_320/<file>.jpg   (cropped to the retina, squared, 320x320)
Safe to re-run: files already converted are skipped."""
import sys
from multiprocessing import Pool
import pandas as pd
from training.settings import *
from training.common import preprocess_image


def work(name):
    out = CACHE / name
    if out.exists():
        return 0
    try:
        preprocess_image(IMG_DIR / name).save(out, quality=95)
        return 1
    except Exception as e:
        print("FAILED", name, e, flush=True)
        return -1


if __name__ == "__main__":
    CACHE.mkdir(parents=True, exist_ok=True)
    names = pd.read_csv(WORK / "labels.csv").disk_filename.tolist()
    done = 0
    with Pool(2) as p:
        for i, r in enumerate(p.imap_unordered(work, names), 1):
            done += r > 0
            if i % 50 == 0:
                print(f"{i}/{len(names)}", flush=True)
    print(f"finished: {done} new images converted, {len(list(CACHE.glob('*.jpg')))} in cache")
