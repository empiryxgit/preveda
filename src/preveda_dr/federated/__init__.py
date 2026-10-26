"""PLANNED - federated learning client (FRD 7, 14.2). Nothing here runs yet.
Design (see docs/decisions/0003-federate-the-final-layer-only.md):
  * only the final classifier layer (2,052 values, ~8 KB) leaves the node, not the 45 MB backbone
  * Flower client, FedProx proximal term (mu=0.01), Opacus DP-SGD, AES-256-GCM payload, nightly 02:00 sync
  * server-side validation: ECDSA-signed global model, rejected if the signature is wrong (ml.registry already does this)
"""
