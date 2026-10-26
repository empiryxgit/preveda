from prometheus_client import Counter, Histogram

PREDICTIONS = Counter("madhu_dr_predictions_total", "DR predictions", ["triage", "model_version"])
LATENCY = Histogram("madhu_dr_predict_seconds", "End-to-end predict latency", buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5))
