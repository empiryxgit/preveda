"""Structured JSON logs (FRD 15.1: Fluentd collects JSON from stdout). Never log patient data - only ids, sizes and timings."""
from __future__ import annotations
import json, logging, sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "level": record.levelname,
               "logger": record.name, "msg": record.getMessage()}
        out.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> logging.Logger:
    log = logging.getLogger("preveda_dr")
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout); h.setFormatter(JsonFormatter()); log.addHandler(h)
    log.setLevel(level); log.propagate = False
    return log


def log_event(msg: str, **fields) -> None:
    logging.getLogger("preveda_dr").info(msg, extra={"extra_fields": fields})
