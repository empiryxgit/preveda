"""Hospital-node data store (FRD 8.1). SQLite = offline fallback, PostgreSQL 16 = primary; same code for both.
Every state change is also written to a hash-chained, append-only audit log (FRD 11.1 Audit Immutability)."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import sqlalchemy as sa

md = sa.MetaData()
results = sa.Table(
    "dr_screening_results", md,
    sa.Column("result_id", sa.String(36), primary_key=True),
    sa.Column("hospital_node_id", sa.String(50), nullable=False),
    sa.Column("patient_hash", sa.String(64)),                     # SHA-256 pseudonym, never a raw ID
    sa.Column("eye", sa.String(10)),
    sa.Column("image_sha256", sa.String(64), nullable=False),
    sa.Column("model_version", sa.String(50), nullable=False),
    sa.Column("model_stage", sa.String(20)),
    sa.Column("prediction", sa.String(20), nullable=False),
    sa.Column("confidence", sa.Float),
    sa.Column("probabilities", sa.JSON),
    sa.Column("flags", sa.JSON),
    sa.Column("triage", sa.String(10), nullable=False),
    sa.Column("ai_finding", sa.Text),
    sa.Column("rationale", sa.Text),
    sa.Column("clinical_context", sa.JSON),
    sa.Column("thumbnail", sa.LargeBinary),
    sa.Column("latency_ms", sa.Float),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("reviewer_id", sa.String(100)),
    sa.Column("confirmed_grade", sa.String(40)),
    sa.Column("review_decision", sa.String(20)),
    sa.Column("review_rationale", sa.Text),
    sa.Column("reviewed_at", sa.DateTime(timezone=True)),
)
audit = sa.Table(
    "audit_log", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", sa.String(40), nullable=False),
    sa.Column("actor", sa.String(100), nullable=False),
    sa.Column("action", sa.String(50), nullable=False),
    sa.Column("resource_id", sa.String(64)),
    sa.Column("details", sa.JSON),
    sa.Column("prev_hash", sa.String(64), nullable=False),
    sa.Column("entry_hash", sa.String(64), nullable=False),
)
app_settings = sa.Table(
    "app_settings", md,
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
)
sa.Index("ix_dr_results_patient", results.c.patient_hash)
sa.Index("ix_dr_results_created", results.c.created_at)
GENESIS = "0" * 64


def _entry_hash(prev: str, ts: str, actor: str, action: str, rid: str | None, details: dict | None) -> str:
    body = json.dumps(details or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{prev}|{ts}|{actor}|{action}|{rid}|{body}".encode()).hexdigest()


class Store:
    def __init__(self, url: str):
        kw = {}
        if url.startswith("sqlite"):
            kw["connect_args"] = {"check_same_thread": False}
            db = sa.engine.make_url(url).database
            if db and db != ":memory:":
                Path(db).parent.mkdir(parents=True, exist_ok=True)
        else:
            kw["pool_pre_ping"] = True
        self.engine = sa.create_engine(url, **kw)
        md.create_all(self.engine)

    def ping(self) -> bool:
        with self.engine.connect() as c:
            c.execute(sa.text("SELECT 1"))
        return True

    def _audit(self, conn, actor: str, action: str, rid: str | None, details: dict | None = None) -> None:
        last = conn.execute(sa.select(audit.c.entry_hash).order_by(audit.c.id.desc()).limit(1).with_for_update()).scalar()
        prev = last or GENESIS
        ts = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        conn.execute(audit.insert().values(ts=ts, actor=actor, action=action, resource_id=rid, details=details or {},
                                           prev_hash=prev, entry_hash=_entry_hash(prev, ts, actor, action, rid, details)))

    def insert_result(self, row: dict, actor: str) -> None:
        row = {**row, "created_at": datetime.now(timezone.utc)}
        with self.engine.begin() as c:
            c.execute(results.insert().values(**row))
            self._audit(c, actor, "DR_PREDICT", row["result_id"],
                        {"triage": row["triage"], "model_version": row["model_version"], "image_sha256": row["image_sha256"]})

    def get_result(self, rid: str) -> dict | None:
        with self.engine.connect() as c:
            r = c.execute(sa.select(results).where(results.c.result_id == rid)).mappings().first()
        return dict(r) if r else None

    def review(self, rid: str, reviewer: str, grade: str, decision: str, rationale: str | None) -> bool:
        with self.engine.begin() as c:
            n = c.execute(results.update().where(results.c.result_id == rid).values(
                reviewer_id=reviewer, confirmed_grade=grade, review_decision=decision,
                review_rationale=rationale, reviewed_at=datetime.now(timezone.utc))).rowcount
            if n:
                self._audit(c, reviewer, "DR_REVIEW", rid, {"confirmed_grade": grade, "decision": decision})
        return bool(n)

    # ---- settings (edited from the web UI) ----
    def settings_map(self) -> dict:
        with self.engine.connect() as c:
            return {r.key: r.value for r in c.execute(sa.select(app_settings))}

    def set_setting(self, key: str, value: str, actor: str) -> None:
        with self.engine.begin() as c:
            c.execute(app_settings.delete().where(app_settings.c.key == key))
            c.execute(app_settings.insert().values(key=key, value=value))
            self._audit(c, actor, "SETTING_CHANGE", key, {"value": value})

    # ---- read models for the dashboard ----
    def has_image(self, sha: str) -> bool:
        with self.engine.connect() as c:
            return c.execute(sa.select(results.c.result_id).where(results.c.image_sha256 == sha).limit(1)).first() is not None

    def list_results(self, triage: str | None = None, q: str | None = None, limit: int = 25, offset: int = 0) -> tuple[list[dict], int]:
        cols = [c for c in results.c if c.name != "thumbnail"]
        cond = []
        if triage:
            cond.append(results.c.triage == triage)
        if q:
            like = f"%{q}%"
            cond.append(sa.or_(sa.cast(results.c.clinical_context, sa.String).ilike(like), results.c.result_id.ilike(like),
                               results.c.prediction.ilike(like)))
        with self.engine.connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(results).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(*cols).where(*cond).order_by(results.c.created_at.desc()).limit(limit).offset(offset)).mappings().all()
        return [dict(r) for r in rows], int(total)

    def stats(self) -> dict:
        with self.engine.connect() as c:
            rows = c.execute(sa.select(results.c.triage, results.c.created_at, results.c.reviewed_at)).all()
        by = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "RETAKE": 0}
        pending, per_day, last = 0, {}, None
        for t, created, reviewed in rows:
            by[t] = by.get(t, 0) + 1
            if t in ("HIGH", "MEDIUM") and reviewed is None:
                pending += 1
            d = created.date().isoformat()
            per_day[d] = per_day.get(d, 0) + 1
            last = max(last, created) if last else created
        return {"total": len(rows), "by_triage": by, "pending_review": pending, "per_day": per_day,
                "last_result_at": last.isoformat() if last else None}

    def audit_tail(self, n: int = 20) -> list[dict]:
        with self.engine.connect() as c:
            rows = c.execute(sa.select(audit.c.id, audit.c.ts, audit.c.actor, audit.c.action, audit.c.resource_id)
                             .order_by(audit.c.id.desc()).limit(n)).mappings().all()
        return [dict(r) for r in rows]

    def verify_audit(self) -> dict:
        """Recompute the hash chain; any edited, deleted or re-ordered row breaks it."""
        prev, n = GENESIS, 0
        with self.engine.connect() as c:
            for r in c.execute(sa.select(audit).order_by(audit.c.id)).mappings():
                ok = r["prev_hash"] == prev and r["entry_hash"] == _entry_hash(
                    prev, r["ts"], r["actor"], r["action"], r["resource_id"], r["details"])
                if not ok:
                    return {"intact": False, "entries": n, "first_bad_id": r["id"]}
                prev, n = r["entry_hash"], n + 1
        return {"intact": True, "entries": n, "first_bad_id": None}
