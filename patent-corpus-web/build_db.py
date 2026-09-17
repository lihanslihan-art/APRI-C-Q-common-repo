#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build corpus.db (SQLite + FTS5) from the upstream standards corpora.

Reads the two read-only corpus trees produced by the upstream agent workspace
and writes a single searchable database:

    <corpus>/catalog.json      document metadata
    <corpus>/text/<id>.json    {"pages": {"1": "...", ...}, "n_pages", ...}
    <corpus>/toc/<id>.json     [{"level", "title", "page"}, ...]

Idempotent: builds into corpus.db.tmp and atomically replaces corpus.db, so a
failed run never leaves a half-built database in place. Nothing is written to
the corpus tree.

Usage:
    python build_db.py                        # both corpora
    python build_db.py --corpus wifi8_tgbn    # one corpus
    python build_db.py --root /path/to/references --out /path/to/corpus.db
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_ROOT = Path(
    os.environ.get(
        "CORPUS_ROOT",
        "/home/admin/ai_patent_experiments/.claude/skills/wifi_patent_skill/references",
    )
)
DEFAULT_OUT = Path(__file__).resolve().parent / "corpus.db"
CORPORA = ("wifi8_tgbn", "ieee_standards")

SCHEMA = """
CREATE TABLE docs (
    corpus            TEXT NOT NULL,
    doc_id            TEXT NOT NULL,
    title             TEXT,
    kind              TEXT,
    ballot            TEXT,
    year              INTEGER,
    author            TEXT,
    doc_date          TEXT,
    first_disclosed   TEXT,
    n_pages           INTEGER,
    url               TEXT,
    family            TEXT,
    scope             TEXT,
    patent_relevance  TEXT,
    PRIMARY KEY (corpus, doc_id)
);
CREATE INDEX docs_kind   ON docs(kind);
CREATE INDEX docs_ballot ON docs(ballot);
CREATE INDEX docs_year   ON docs(year);

CREATE TABLE doc_topics (
    corpus TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    topic  TEXT NOT NULL,
    score  REAL
);
CREATE INDEX doc_topics_topic ON doc_topics(topic);
CREATE INDEX doc_topics_doc   ON doc_topics(corpus, doc_id);

CREATE TABLE toc (
    corpus TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    seq    INTEGER NOT NULL,
    level  INTEGER,
    title  TEXT,
    page   INTEGER
);
CREATE INDEX toc_doc ON toc(corpus, doc_id, seq);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);

CREATE VIRTUAL TABLE pages USING fts5(
    corpus UNINDEXED,
    doc_id UNINDEXED,
    page   UNINDEXED,
    body
);
"""


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def load_tgbn_docs(root: Path) -> list[dict]:
    """The TGbn catalog is {"documents": [ {...}, ... ]}."""
    cat = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    out = []
    for d in cat.get("documents", []):
        out.append(
            {
                "doc_id": d["doc_id"],
                "title": d.get("title"),
                "kind": d.get("kind"),
                "ballot": d.get("ballot"),
                "year": _int(d.get("year")),
                "author": d.get("author"),
                "doc_date": d.get("date"),
                # first_disclosed is the r0 date: the correct prior-art basis,
                # not the latest-revision date.
                "first_disclosed": d.get("first_disclosed"),
                "n_pages": _int(d.get("n_pages")),
                "url": d.get("url"),
                "family": d.get("group"),
                "scope": None,
                "patent_relevance": None,
                "topics": d.get("topics") or [],
                "topic_scores": d.get("topic_scores") or {},
            }
        )
    return out


def load_ieee_docs(root: Path) -> list[dict]:
    """The IEEE catalog is {"standards": [ {...}, ... ]} keyed by pdf_id."""
    cat = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    out = []
    for d in cat.get("standards", []):
        year = _int(d.get("year"))
        out.append(
            {
                "doc_id": d["pdf_id"],
                "title": d.get("title"),
                "kind": d.get("kind"),
                "ballot": None,
                "year": year,
                "author": None,
                "doc_date": str(year) if year else None,
                # A published standard's disclosure date is its publication year.
                "first_disclosed": f"{year}-01-01" if year else None,
                "n_pages": None,
                "url": None,
                "family": d.get("family"),
                "scope": d.get("scope"),
                "patent_relevance": d.get("patent_relevance"),
                "topics": [],
                "topic_scores": {},
            }
        )
    return out


LOADERS = {"wifi8_tgbn": load_tgbn_docs, "ieee_standards": load_ieee_docs}


def ingest(con: sqlite3.Connection, root: Path, corpus: str) -> tuple[int, int]:
    croot = root / corpus
    if not croot.is_dir():
        raise SystemExit(f"corpus tree not found: {croot}")

    docs = LOADERS[corpus](croot)
    con.executemany(
        """INSERT OR REPLACE INTO docs
           (corpus, doc_id, title, kind, ballot, year, author, doc_date,
            first_disclosed, n_pages, url, family, scope, patent_relevance)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                corpus, d["doc_id"], d["title"], d["kind"], d["ballot"], d["year"],
                d["author"], d["doc_date"], d["first_disclosed"], d["n_pages"],
                d["url"], d["family"], d["scope"], d["patent_relevance"],
            )
            for d in docs
        ],
    )
    con.executemany(
        "INSERT INTO doc_topics (corpus, doc_id, topic, score) VALUES (?,?,?,?)",
        [
            (corpus, d["doc_id"], t, (d["topic_scores"] or {}).get(t))
            for d in docs
            for t in d["topics"]
        ],
    )

    # Pages: the FTS payload. Only documents that actually have text appear.
    n_pages = 0
    text_dir = croot / "text"
    for f in sorted(text_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  ! skipping unreadable {f.name}: {e}", file=sys.stderr)
            continue
        rows = [
            (corpus, f.stem, str(p), body)
            for p, body in (data.get("pages") or {}).items()
            if body and body.strip()
        ]
        if rows:
            con.executemany("INSERT INTO pages VALUES (?,?,?,?)", rows)
            n_pages += len(rows)

    # Table of contents, for the document reader view.
    toc_dir = croot / "toc"
    if toc_dir.is_dir():
        for f in sorted(toc_dir.glob("*.json")):
            try:
                entries = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(entries, list):
                continue
            con.executemany(
                "INSERT INTO toc (corpus, doc_id, seq, level, title, page) VALUES (?,?,?,?,?,?)",
                [
                    (corpus, f.stem, i, _int(e.get("level")), e.get("title"), _int(e.get("page")))
                    for i, e in enumerate(entries)
                    if isinstance(e, dict)
                ],
            )
    con.commit()
    return len(docs), n_pages


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                    help="corpus references/ directory (read-only)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output database")
    ap.add_argument("--corpus", action="append", choices=CORPORA,
                    help="limit to one corpus (repeatable); default: all")
    args = ap.parse_args(argv)

    corpora = args.corpus or list(CORPORA)
    tmp = args.out.with_suffix(args.out.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    con = sqlite3.connect(tmp)
    # Safe: a crash discards the .tmp file and corpus.db is untouched.
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.executescript(SCHEMA)

    totals = {}
    for corpus in corpora:
        print(f"[{corpus}] ingesting from {args.root / corpus} ...")
        nd, np_ = ingest(con, args.root, corpus)
        totals[corpus] = (nd, np_)
        print(f"[{corpus}] {nd:,} documents, {np_:,} pages")

    print("optimising FTS index ...")
    con.execute("INSERT INTO pages(pages) VALUES('optimize')")
    con.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
        [
            ("built_at", time.strftime("%Y-%m-%dT%H:%M:%S%z")),
            ("corpus_root", str(args.root)),
            ("corpora", json.dumps(corpora)),
            ("totals", json.dumps({k: {"documents": v[0], "pages": v[1]}
                                   for k, v in totals.items()})),
            ("schema_version", "1"),
        ],
    )
    con.commit()
    con.execute("VACUUM")
    con.close()

    os.replace(tmp, args.out)
    size = args.out.stat().st_size / 1e6
    print(f"\nwrote {args.out}  ({size:.0f} MB) in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
