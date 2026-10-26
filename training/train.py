"""STEP 3 - Train the model.
Model  : ResNet-18 (ImageNet pre-trained), final layer replaced by a 4-class head.
Split  : by PATIENT (both eyes of one patient never straddle train/val/test) -> honest scores.
Reads  : work/labels.csv, work/images_320/
Writes : model/best.pt, model/reference_embeddings.npz, work/split.csv, work/metrics.json"""
import json, random, time
import numpy as np, pandas as pd, torch, torch.nn as nn
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms as T
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from training.settings import *

random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
MODEL.mkdir(parents=True, exist_ok=True)
import os
torch.set_num_threads(os.cpu_count() or 2)
dev = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", dev, "| mode:", TRAIN_MODE, "| threads:", torch.get_num_threads())


class Net(nn.Module):
    """ResNet-18 that returns (class scores, 512-number image 'fingerprint')."""
    def __init__(self, n_classes=len(CLASSES), pretrained=True):
        super().__init__()
        try:
            r = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None)
        except Exception as e:
            print("!! could not download pre-trained weights, training from scratch:", e)
            r = models.resnet18(weights=None)
        self.features = nn.Sequential(*list(r.children())[:-1])   # everything up to global pooling
        self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(512, n_classes))

    def forward(self, x):
        emb = self.features(x).flatten(1)
        return self.head(emb), emb


class DS(Dataset):
    def __init__(self, df, train):
        self.df, self.cls = df.reset_index(drop=True), {c: i for i, c in enumerate(CLASSES)}
        norm = T.Compose([T.ToTensor(), T.Normalize(MEAN, STD)])
        self.tf = T.Compose([T.RandomHorizontalFlip(), T.RandomVerticalFlip(), T.RandomRotation(20),
                             T.ColorJitter(0.25, 0.25, 0.15), T.RandomResizedCrop(IMG_SIZE, (0.85, 1.0)),
                             norm]) if train else norm

    def __len__(self): return len(self.df)

    def __getitem__(self, i):
        r = self.df.iloc[i]
        return self.tf(Image.open(CACHE / r.disk_filename).convert("RGB")), self.cls[r.diagnosis]


def loader(df, train):
    return DataLoader(DS(df, train), batch_size=BATCH_SIZE, shuffle=train, num_workers=0)


@torch.no_grad()
def run(model, dl):
    model.eval(); P, Y, E = [], [], []
    for x, y in dl:
        lo, em = model(x.to(dev)); P.append(lo.softmax(1).cpu()); E.append(em.cpu()); Y.append(y)
    return torch.cat(P).numpy(), torch.cat(Y).numpy(), torch.cat(E).numpy()


if __name__ == "__main__":
    df = pd.read_csv(WORK / "labels.csv")
    df = df[df.disk_filename.apply(lambda f: (CACHE / f).exists())].reset_index(drop=True)
    y = df.diagnosis.map({c: i for i, c in enumerate(CLASSES)})
    # 80/20 train+val vs test, then 80/20 train vs val - always grouped by patient
    tr_i, te_i = next(StratifiedGroupKFold(5, shuffle=True, random_state=SEED).split(df, y, df.patient))
    sub = df.iloc[tr_i].reset_index(drop=True)
    t2, v2 = next(StratifiedGroupKFold(5, shuffle=True, random_state=SEED).split(sub, y.iloc[tr_i].values, sub.patient))
    train, val, test = sub.iloc[t2], sub.iloc[v2], df.iloc[te_i]
    df["split"] = "train"; df.loc[sub.index[v2].map(lambda k: tr_i[k]), "split"] = "val"; df.loc[te_i, "split"] = "test"
    df.to_csv(WORK / "split.csv", index=False)
    print({k: len(v) for k, v in dict(train=train, val=val, test=test).items()})

    counts = train.diagnosis.value_counts().reindex(CLASSES).values.astype(float)
    w = torch.tensor((counts.sum() / counts) ** 0.5, dtype=torch.float32); w = (w / w.mean()).to(dev)
    model = Net().to(dev)
    # freeze part of the backbone so a CPU has less to compute
    n_frozen = len(model.features) if TRAIN_MODE == "fast" else 6   # 6 = conv1,bn1,relu,pool,layer1,layer2
    frozen = list(model.features.children())[:n_frozen]
    for m in frozen:
        for p in m.parameters(): p.requires_grad = False

    def set_train():
        model.train()
        for m in frozen: m.eval()      # keep frozen BatchNorm statistics fixed
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=3e-4, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, EPOCHS)
    lossf = nn.CrossEntropyLoss(weight=w, label_smoothing=0.05)
    dl_tr, dl_va = loader(train, True), loader(val, False)
    best, bad = -1, 0
    for ep in range(1, EPOCHS + 1):
        set_train(); t0 = time.time(); tot = 0
        for x, yy in dl_tr:
            opt.zero_grad(); lo, _ = model(x.to(dev)); l = lossf(lo, yy.to(dev)); l.backward(); opt.step(); tot += l.item()
        sched.step()
        P, Y, _ = run(model, dl_va); f1 = f1_score(Y, P.argmax(1), average="macro")
        print(f"epoch {ep:02d} loss {tot/len(dl_tr):.3f} val acc {(P.argmax(1)==Y).mean():.3f} val macroF1 {f1:.3f} ({time.time()-t0:.0f}s)", flush=True)
        if f1 > best:
            best, bad = f1, 0; torch.save(model.state_dict(), MODEL / "best.pt")
        else:
            bad += 1
            if bad >= 6: print("early stop"); break

    model.load_state_dict(torch.load(MODEL / "best.pt", map_location=dev))
    P, Y, _ = run(model, loader(test, False)); pred = P.argmax(1)
    rep = classification_report(Y, pred, labels=range(len(CLASSES)), target_names=CLASSES, output_dict=True, zero_division=0)
    cm = confusion_matrix(Y, pred, labels=range(len(CLASSES))).tolist()
    dr = CLASSES.index("DR")
    metrics = dict(n_train=len(train), n_val=len(val), n_test=len(test), best_val_macro_f1=best,
                   test_accuracy=float((pred == Y).mean()), test_report=rep, confusion_matrix=cm, classes=CLASSES,
                   dr_sensitivity=float(((pred == dr) & (Y == dr)).sum() / max((Y == dr).sum(), 1)),
                   dr_test_images=int((Y == dr).sum()))
    json.dump(metrics, open(WORK / "metrics.json", "w"), indent=2)
    print(classification_report(Y, pred, labels=range(len(CLASSES)), target_names=CLASSES, zero_division=0))
    print("confusion matrix (rows=true, cols=predicted):", CLASSES); print(np.array(cm))

    # ---- the "pattern": what a typical image of each class looks like inside the network ----
    P, Y, E = run(model, loader(train, False))
    E = E / np.linalg.norm(E, axis=1, keepdims=True)
    cent = np.stack([E[Y == i].mean(0) for i in range(len(CLASSES))]); cent /= np.linalg.norm(cent, axis=1, keepdims=True)
    thr = np.array([np.percentile(1 - E[Y == i] @ cent[i], 95) for i in range(len(CLASSES))])
    np.savez(MODEL / "reference_embeddings.npz", centroids=cent, novelty_threshold=thr, classes=np.array(CLASSES))
    print("saved model/best.pt and model/reference_embeddings.npz")
