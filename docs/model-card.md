# Model card - Madhu-DR 1.0.0 (STAGING)

- **Task:** 4-class fundus screening: Ungradable / Healthy / DR / Other. Severity grade is NOT predicted.
- **Architecture:** ResNet-18 (ImageNet), conv1..layer2 frozen, 320x320 input, ONNX (outputs `logits`, `embedding`).
- **Data:** 921 fundus images, patient-level StratifiedGroupKFold (~64/16/20). Training used 590 images.
- **Results (held-out test):** AUROC about 0.80. DR sensitivity 47% at argmax, 53% at P(DR)>=0.40, 71% at 0.15 with 78% specificity. Only 17 DR test images, so intervals are wide.
- **Intended use:** triage aid for clinician review. Not a diagnosis. A LOW result does not rule out DR.
- **Known limits:** single source, small, no per-site labels (fairness not assessed), guideline text is a clinician-owned DRAFT.
- **Not for:** autonomous decisions, dosing, screening without clinician sign-off.
