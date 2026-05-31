"""SQLite store for runs / sims / findings / clusters. stdlib sqlite3.

MVP persistence (single file, zero ops). Graduates to Postgres for thousands of
sims — kept in its OWN schema, never the Resonate app tables.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .flagging import Cluster, SimVerdict

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at REAL, mode TEXT, target TEXT,
  sim_count INTEGER, flagged INTEGER, config TEXT);
CREATE TABLE IF NOT EXISTS sims(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, sim_id TEXT, channel TEXT,
  intent_type TEXT, model TEXT, persona TEXT, surface TEXT, quality_score REAL,
  reviews_json TEXT, preflight_qa_json TEXT, severity TEXT, finding_count INTEGER);
CREATE TABLE IF NOT EXISTS findings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, sim_id TEXT, dimension TEXT,
  severity TEXT, source TEXT, detail TEXT, evidence TEXT);
CREATE TABLE IF NOT EXISTS clusters(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, dimension TEXT, severity TEXT,
  size INTEGER, channels TEXT, example_sim_id TEXT, example_evidence TEXT);
"""


class Store:
    def __init__(self, path: str = "runs/harness.db") -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)

    def save_run(self, mode: str, target: str, verdicts: list[SimVerdict],
                 clusters: list[Cluster], config: dict | None = None) -> int:
        cur = self.db.cursor()
        flagged = sum(1 for v in verdicts if not v.passed)
        cur.execute(
            "INSERT INTO runs(started_at,mode,target,sim_count,flagged,config) VALUES(?,?,?,?,?,?)",
            (time.time(), mode, target, len(verdicts), flagged, json.dumps(config or {})),
        )
        run_id = cur.lastrowid
        for v in verdicts:
            cur.execute(
                "INSERT INTO sims(run_id,sim_id,channel,intent_type,model,persona,surface,quality_score,"
                "reviews_json,preflight_qa_json,severity,finding_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, v.sim_id, v.channel, v.intent_type, v.model, v.persona, v.surface, v.quality_score,
                 json.dumps(v.reviews or []), json.dumps(v.preflight_qa or []),
                 v.severity.value if v.severity else "pass", len(v.findings)),
            )
            for f in v.findings:
                cur.execute(
                    "INSERT INTO findings(run_id,sim_id,dimension,severity,source,detail,evidence) VALUES(?,?,?,?,?,?,?)",
                    (run_id, v.sim_id, f.dimension, f.severity.value, f.source, f.detail, f.evidence),
                )
        for c in clusters:
            cur.execute(
                "INSERT INTO clusters(run_id,dimension,severity,size,channels,example_sim_id,example_evidence) "
                "VALUES(?,?,?,?,?,?,?)",
                (run_id, c.dimension, c.severity.value, c.size, json.dumps(c.channels), c.example_sim_id, c.example_evidence),
            )
        self.db.commit()
        return run_id

    # ── read API (powers the dashboard) ──────────────────────────────────────
    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def list_runs(self) -> list[dict]:
        return self._rows("SELECT * FROM runs ORDER BY id DESC")

    def sims_for_run(self, run_id: int) -> list[dict]:
        return self._rows("SELECT * FROM sims WHERE run_id=? ORDER BY id", (run_id,))

    def findings_for_run(self, run_id: int) -> list[dict]:
        return self._rows("SELECT * FROM findings WHERE run_id=? ORDER BY id", (run_id,))

    def clusters_for_run(self, run_id: int) -> list[dict]:
        return self._rows("SELECT * FROM clusters WHERE run_id=? ORDER BY size DESC", (run_id,))
