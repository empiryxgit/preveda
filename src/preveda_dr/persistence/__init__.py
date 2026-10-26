"""Hospital-node storage (FRD 8.1): results table + hash-chained audit log on SQLite or PostgreSQL."""
from .db import Store

__all__ = ["Store"]
