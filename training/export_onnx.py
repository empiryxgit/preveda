"""STEP 4 - Freeze the trained model into an ONNX file + a pattern.json that describes how to use it.
Reads : model/best.pt, model/reference_embeddings.npz, work/metrics.json
Writes: model/dr_model.onnx, model/pattern.json"""
import json, datetime, hashlib
import numpy as np, torch, onnxruntime as ort
from training.settings import *
from training.train import Net

net = Net(pretrained=False); net.load_state_dict(torch.load(MODEL / "best.pt", map_location="cpu")); net.eval()
dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE)
kw = dict(input_names=["image"], output_names=["logits", "embedding"], opset_version=17,
          dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}, "embedding": {0: "batch"}})
try:
    torch.onnx.export(net, dummy, str(MODEL / "dr_model.onnx"), dynamo=False, **kw)
except TypeError:
    torch.onnx.export(net, dummy, str(MODEL / "dr_model.onnx"), **kw)

# prove the ONNX file gives the same answers as the PyTorch model
x = torch.randn(4, 3, IMG_SIZE, IMG_SIZE)
with torch.no_grad(): ref = net(x)[0].numpy()
got = ort.InferenceSession(str(MODEL / "dr_model.onnx"), providers=["CPUExecutionProvider"]).run(None, {"image": x.numpy()})[0]
diff = float(np.abs(ref - got).max()); print("max difference PyTorch vs ONNX:", diff); assert diff < 1e-3

ref_e = np.load(MODEL / "reference_embeddings.npz"); m = json.load(open(WORK / "metrics.json"))
pattern = dict(
    created=datetime.datetime.now().isoformat(timespec="seconds"),
    onnx_file="dr_model.onnx", onnx_sha256=hashlib.sha256((MODEL / "dr_model.onnx").read_bytes()).hexdigest(),
    architecture="ResNet-18 (ImageNet pre-trained, fine-tuned), 4-class head, 512-d embedding output",
    classes=CLASSES, input=dict(name="image", shape=[None, 3, IMG_SIZE, IMG_SIZE], mean=MEAN, std=STD),
    preprocessing=["open RGB", "crop black border (max channel <= 12)", "pad to square", f"resize {IMG_SIZE}x{IMG_SIZE} bilinear",
                   "scale to 0-1", "normalise with mean/std"],
    outputs=dict(logits="softmax -> class probabilities", embedding="512-d fingerprint (L2-normalise before comparing)"),
    low_confidence_below=0.5,
    novelty=dict(method="cosine distance to the predicted class centroid in model/reference_embeddings.npz",
                 threshold_per_class=dict(zip(CLASSES, [float(t) for t in ref_e["novelty_threshold"]]))),
    training=dict(n_train=m["n_train"], n_val=m["n_val"], n_test=m["n_test"], test_accuracy=m["test_accuracy"],
                  test_per_class_f1={c: m["test_report"][c]["f1-score"] for c in CLASSES},
                  dr_sensitivity=m["dr_sensitivity"], dr_test_images=m["dr_test_images"]),
)
json.dump(pattern, open(MODEL / "pattern.json", "w"), indent=2)
print("saved model/dr_model.onnx and model/pattern.json")

# ---- register the freshly exported model: sign it and put it where the service loads it from ----
from training.build_registry import main as _register
from training.settings import ROOT
import sys
_register(["--onnx", str(MODEL / "dr_model.onnx"), "--embeddings", str(MODEL / "reference_embeddings.npz"),
           "--pattern", str(MODEL / "pattern.json"), "--split", str(WORK / "split.csv"), "--cache", str(CACHE),
           "--version", sys.argv[1] if len(sys.argv) > 1 else "1.0.0", "--init-keys"])
