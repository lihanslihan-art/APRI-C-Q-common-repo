#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Job store and state machine for the drafting workbench.

A job is one patent idea moving through the upstream skill's own gates:

    queued -> screening -> awaiting_approval -> drafting -> done
                    |              |               |
                    +-> failed     +-> rejected    +-> failed

`screening` runs the skill's mandatory prior-art gate and pre-drafting
analysis. It stops there on purpose: the upstream skill says to wait for the
user's explicit go-ahead before drafting, so the gate is a real pause, not a
formality. `drafting` resumes the *same* agent session, so the analysis stays
in context instead of being re-derived.

Events are not stored here. They are appended to runs/<job_id>/events.jsonl,
which is the raw stream-json from the agent and can be large.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
RUNS = Path(__file__).resolve().parent / "runs"

QUEUED = "queued"
SCREENING = "screening"
AWAITING_APPROVAL = "awaiting_approval"
DRAFTING = "drafting"
DONE = "done"
FAILED = "failed"
REJECTED = "rejected"
CANCELLED = "cancelled"

ACTIVE = (SCREENING, DRAFTING)
TERMINAL = (DONE, FAILED, REJECTED, CANCELLED)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    idea          TEXT NOT NULL,
    track         TEXT NOT NULL DEFAULT 'std',
    status        TEXT NOT NULL,
    session_id    TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL,
    cost_usd      REAL NOT NULL DEFAULT 0,
    num_turns     INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    screen_summary TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_created ON jobs(created_at DESC);
"""


class Store:
    def __init__(self, path: Path | None = None):
        RUNS.mkdir(parents=True, exist_ok=True)
        self.path = path or (RUNS / "jobs.db")
        self._lock = threading.Lock()
        self._con = sqlite3.connect(self.path, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.executescript(SCHEMA)
        self._con.commit()

    # ---------------- writes ----------------

    def create(self, title: str, idea: str, track: str = "std") -> str:
        job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        now = time.time()
        with self._lock:
            self._con.execute(
                "INSERT INTO jobs (id, title, idea, track, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (job_id, title, idea, track, QUEUED, now, now),
            )
            self._con.commit()
        self.run_dir(job_id).mkdir(parents=True, exist_ok=True)
        return job_id

    def update(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._con.execute(
                f"UPDATE jobs SET {cols} WHERE id = ?", [*fields.values(), job_id]
            )
            self._con.commit()

    def set_status(self, job_id: str, status: str, **extra: Any) -> None:
        if status in ACTIVE and "started_at" not in extra:
            cur = self.get(job_id)
            if cur and not cur.get("started_at"):
                extra["started_at"] = time.time()
        if status in TERMINAL:
            extra.setdefault("finished_at", time.time())
        self.update(job_id, status=status, **extra)

    def add_cost(self, job_id: str, cost: float, turns: int = 0) -> None:
        with self._lock:
            self._con.execute(
                "UPDATE jobs SET cost_usd = cost_usd + ?, num_turns = num_turns + ?, "
                "updated_at = ? WHERE id = ?",
                (cost or 0, turns or 0, time.time(), job_id),
            )
            self._con.commit()

    # ---------------- reads ----------------

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            r = self._con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(r) if r else None

    def list(self, limit: int = 50, status: str | None = None) -> list[dict]:
        q = "SELECT * FROM jobs"
        params: list[Any] = []
        if status:
            q += " WHERE status = ?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._con.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def count_active(self) -> int:
        with self._lock:
            r = self._con.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN (?,?)", ACTIVE
            ).fetchone()
        return r[0]

    def next_queued(self) -> dict | None:
        with self._lock:
            r = self._con.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at LIMIT 1", (QUEUED,)
            ).fetchone()
        return dict(r) if r else None

    # ---------------- run directory ----------------

    def run_dir(self, job_id: str) -> Path:
        return RUNS / job_id

    def events_path(self, job_id: str) -> Path:
        return self.run_dir(job_id) / "events.jsonl"

    def output_dir(self, job_id: str) -> Path:
        return self.run_dir(job_id) / "output"

    def append_event(self, job_id: str, event: dict) -> None:
        p = self.events_path(job_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def read_events(self, job_id: str, since: int = 0) -> list[dict]:
        p = self.events_path(job_id)
        if not p.exists():
            return []
        out = []
        with p.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < since or not line.strip():
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def artifacts(self, job_id: str) -> list[dict]:
        """Files the agent produced, relative to the job's output directory."""
        out = self.output_dir(job_id)
        if not out.is_dir():
            return []
        # Build noise, not deliverables: the agent imports pptx_helpers, which
        # leaves a .pyc behind that otherwise shows up as an artifact.
        noise = {"__pycache__", ".ipynb_checkpoints"}
        items = []
        for p in sorted(out.rglob("*")):
            if noise & set(p.parts) or p.suffix == ".pyc":
                continue
            if p.is_file():
                items.append(
                    {
                        "path": str(p.relative_to(out)),
                        "bytes": p.stat().st_size,
                        "modified": p.stat().st_mtime,
                    }
                )
        return items


store = Store()
