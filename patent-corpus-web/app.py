#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patent corpus search service.

Serves full-text search over the IEEE 802 standards corpus and the Wi-Fi 8
(IEEE P802.11bn / TGbn) working-group corpus, backed by SQLite FTS5.

The database is opened read-only and the corpus tree is never touched, so this
service cannot alter the upstream workspace it reads from.

Run:
    uvicorn app:app --host 127.0.0.1 --port 3014
"""
from __future__ import annotations

import html
import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CORPUS_DB", BASE / "corpus.db"))
WEB_DIR = BASE / "web"
MAX_LIMIT = 200
# Counting every match is cheap on this index, but a pathological query (a
# stopword-like token hitting most of the corpus) should not stall the request.
COUNT_CEILING = 50_000

Mode = Literal["token", "phrase", "boolean", "prefix"]
FTS_OPS = {"AND", "OR", "NOT", "NEAR"}

_con: sqlite3.Connection | None = None


# FTS5's snippet() does not escape its input, so a corpus page containing
# "<script>" would be injected verbatim into any HTML consumer. Highlight with
# private-use sentinels instead, then escape and re-mark server-side.
HL_OPEN = "\ue000"
HL_CLOSE = "\ue001"


def render_snippet(raw: str) -> tuple[str, str]:
    """Return (plain_text, safe_html) for a sentinel-marked snippet."""
    if raw is None:
        return "", ""
    plain = raw.replace(HL_OPEN, "").replace(HL_CLOSE, "")
    safe = (
        html.escape(raw, quote=False)
        .replace(HL_OPEN, "<mark>")
        .replace(HL_CLOSE, "</mark>")
    )
    return plain, safe


# --------------------------------------------------------------------------
# FTS5 query construction
# --------------------------------------------------------------------------

def _quote(term: str) -> str:
    """Wrap a term as an FTS5 string literal.

    This is not cosmetic. FTS5 parses a bare hyphenated token like `co-tdma`
    as a column reference and fails with "no such column: tdma", so every
    user-supplied term has to be quoted before it reaches MATCH.
    """
    return '"' + term.replace('"', '""') + '"'


def build_match(q: str, mode: Mode) -> str:
    q = q.strip()
    if not q:
        raise ValueError("empty query")

    if mode == "phrase":
        return _quote(q)

    tokens = q.split()

    if mode == "token":
        return " AND ".join(_quote(t) for t in tokens)

    if mode == "prefix":
        return " AND ".join(_quote(t.rstrip("*")) + "*" for t in tokens if t.rstrip("*"))

    # boolean: keep the operators and parentheses, quote everything else.
    out: list[str] = []
    for tok in tokens:
        upper = tok.upper()
        if upper in FTS_OPS:
            out.append(upper)
            continue
        if tok.startswith('"') and tok.endswith('"') and len(tok) > 1:
            out.append(tok)
            continue
        star = tok.endswith("*")
        core = tok[:-1] if star else tok
        lead = trail = ""
        while core.startswith("("):
            lead += "("
            core = core[1:]
        while core.endswith(")"):
            trail = ")" + trail
            core = core[:-1]
        if not core:
            out.append(lead + trail)
            continue
        out.append(lead + _quote(core) + ("*" if star else "") + trail)
    built = " ".join(x for x in out if x)
    if not built:
        raise ValueError("query reduced to nothing")
    # A query made only of operators and parentheses has no search terms;
    # catch it here so the caller gets a clear message instead of an opaque
    # FTS5 syntax error from SQLite.
    if not any('"' in x for x in out):
        raise ValueError("query has no search terms, only operators")
    return built


# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------

def _filters(corpus, kind, ballot, year, topic) -> tuple[str, list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if corpus:
        where.append("d.corpus = ?")
        params.append(corpus)
    if kind:
        where.append("d.kind = ?")
        params.append(kind)
    if ballot:
        where.append("d.ballot = ?")
        params.append(ballot)
    if year:
        where.append("d.year = ?")
        params.append(year)
    if topic:
        where.append(
            "EXISTS (SELECT 1 FROM doc_topics t "
            "WHERE t.corpus = d.corpus AND t.doc_id = d.doc_id AND t.topic = ?)"
        )
        params.append(topic)
    return (" AND " + " AND ".join(where) if where else ""), params


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _con
    if not DB_PATH.exists():
        raise RuntimeError(
            f"{DB_PATH} is missing. Build it first: python build_db.py"
        )
    _con = sqlite3.connect(
        f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False
    )
    _con.row_factory = sqlite3.Row
    yield
    _con.close()
    _con = None


app = FastAPI(
    title="Patent Corpus Search",
    description="Full-text search over the IEEE 802 and Wi-Fi 8 (TGbn) corpora.",
    version="1.0.0",
    lifespan=lifespan,
)


def db() -> sqlite3.Connection:
    if _con is None:
        raise HTTPException(503, "database not ready")
    return _con


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    try:
        db().execute("SELECT 1 FROM pages LIMIT 1").fetchone()
        return {"ok": True}
    except Exception as e:  # surfaced to the reverse proxy / systemd
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)


@app.get("/api/stats")
def stats():
    con = db()
    meta = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM meta")}
    per_corpus = [
        dict(r)
        for r in con.execute(
            """SELECT d.corpus,
                      COUNT(*) AS documents,
                      (SELECT COUNT(*) FROM pages p WHERE p.corpus = d.corpus) AS pages
               FROM docs d GROUP BY d.corpus ORDER BY d.corpus"""
        )
    ]
    return {
        "built_at": meta.get("built_at"),
        "corpus_root": meta.get("corpus_root"),
        "schema_version": meta.get("schema_version"),
        "documents": sum(c["documents"] for c in per_corpus),
        "pages": sum(c["pages"] for c in per_corpus),
        "db_bytes": DB_PATH.stat().st_size,
        "per_corpus": per_corpus,
    }


@app.get("/api/facets")
def facets(corpus: str | None = None):
    con = db()
    clause, params = _filters(corpus, None, None, None, None)
    clause = clause.replace(" AND ", " WHERE ", 1) if clause else ""

    def group(col: str):
        return [
            {"value": r[0], "count": r[1]}
            for r in con.execute(
                f"SELECT d.{col}, COUNT(*) FROM docs d{clause} "
                f"{'AND' if clause else 'WHERE'} d.{col} IS NOT NULL "
                f"GROUP BY d.{col} ORDER BY COUNT(*) DESC",
                params,
            )
        ]

    topics = [
        {"value": r[0], "count": r[1]}
        for r in con.execute(
            "SELECT t.topic, COUNT(DISTINCT t.corpus || t.doc_id) FROM doc_topics t "
            + ("JOIN docs d ON d.corpus = t.corpus AND d.doc_id = t.doc_id WHERE d.corpus = ? " if corpus else "")
            + "GROUP BY t.topic ORDER BY 2 DESC",
            ([corpus] if corpus else []),
        )
    ]
    return {
        "corpus": group("corpus"),
        "kind": group("kind"),
        "ballot": group("ballot"),
        "year": group("year"),
        "topic": topics,
    }


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1, max_length=500, description="query string"),
    mode: Mode = "token",
    corpus: str | None = None,
    kind: str | None = None,
    topic: str | None = None,
    ballot: str | None = None,
    year: int | None = None,
    limit: int = Query(20, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    snippet_tokens: int = Query(16, ge=4, le=64),
):
    con = db()
    try:
        match = build_match(q, mode)
    except ValueError as e:
        raise HTTPException(400, str(e))

    clause, fparams = _filters(corpus, kind, ballot, year, topic)
    t0 = time.perf_counter()

    sql = f"""
        SELECT p.corpus, p.doc_id, p.page,
               snippet(pages, 3, ?, ?, '…', ?) AS snippet,
               bm25(pages) AS score,
               d.title, d.kind, d.ballot, d.year, d.author,
               d.first_disclosed, d.url, d.family
          FROM pages p
          JOIN docs d ON d.corpus = p.corpus AND d.doc_id = p.doc_id
         WHERE pages MATCH ?{clause}
         ORDER BY score
         LIMIT ? OFFSET ?
    """
    try:
        rows = con.execute(
            sql, [HL_OPEN, HL_CLOSE, snippet_tokens, match, *fparams, limit, offset]
        ).fetchall()
        total = con.execute(
            f"""SELECT COUNT(*) FROM (
                   SELECT 1 FROM pages p
                     JOIN docs d ON d.corpus = p.corpus AND d.doc_id = p.doc_id
                    WHERE pages MATCH ?{clause} LIMIT ?)""",
            [match, *fparams, COUNT_CEILING],
        ).fetchone()[0]
    except sqlite3.OperationalError as e:
        # Malformed FTS5 syntax in boolean mode lands here.
        raise HTTPException(400, f"bad query: {e}")

    results = []
    for r in rows:
        plain, safe = render_snippet(r["snippet"])
        results.append(
            {
                "corpus": r["corpus"],
                "doc_id": r["doc_id"],
                "page": int(r["page"]) if str(r["page"]).isdigit() else r["page"],
                "snippet": plain,
                "snippet_html": safe,
                "score": round(r["score"], 4),
                "title": r["title"],
                "kind": r["kind"],
                "ballot": r["ballot"],
                "year": r["year"],
                "author": r["author"],
                # The r0 date, not the latest revision: the correct basis for
                # a prior-art cutoff.
                "first_disclosed": r["first_disclosed"],
                "url": r["url"],
                "family": r["family"],
            }
        )

    return {
        "query": q,
        "mode": mode,
        "match": match,
        "total": total,
        "total_capped": total >= COUNT_CEILING,
        "limit": limit,
        "offset": offset,
        "took_ms": round((time.perf_counter() - t0) * 1000, 1),
        "results": results,
    }


def _resolve_doc(doc_id: str, corpus: str | None) -> sqlite3.Row:
    con = db()
    if corpus:
        row = con.execute(
            "SELECT * FROM docs WHERE corpus = ? AND doc_id = ?", (corpus, doc_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"no such document: {corpus}/{doc_id}")
        return row
    rows = con.execute("SELECT * FROM docs WHERE doc_id = ?", (doc_id,)).fetchall()
    if not rows:
        raise HTTPException(404, f"no such document: {doc_id}")
    if len(rows) > 1:
        raise HTTPException(
            409,
            f"{doc_id} exists in {len(rows)} corpora; pass ?corpus= to disambiguate",
        )
    return rows[0]


@app.get("/api/doc/{doc_id}")
def get_doc(doc_id: str, corpus: str | None = None):
    con = db()
    row = _resolve_doc(doc_id, corpus)
    c, d = row["corpus"], row["doc_id"]
    toc = [
        dict(r)
        for r in con.execute(
            "SELECT level, title, page FROM toc WHERE corpus = ? AND doc_id = ? ORDER BY seq",
            (c, d),
        )
    ]
    topics = [
        {"topic": r[0], "score": r[1]}
        for r in con.execute(
            "SELECT topic, score FROM doc_topics WHERE corpus = ? AND doc_id = ? "
            "ORDER BY score DESC NULLS LAST",
            (c, d),
        )
    ]
    pages = [
        int(r[0]) if str(r[0]).isdigit() else r[0]
        for r in con.execute(
            "SELECT page FROM pages WHERE corpus = ? AND doc_id = ?", (c, d)
        )
    ]
    doc = {k: row[k] for k in row.keys()}
    doc["topics"] = topics
    doc["toc"] = toc
    doc["pages_with_text"] = sorted(p for p in pages if isinstance(p, int))
    return doc


@app.get("/api/doc/{doc_id}/page/{page}")
def get_page(doc_id: str, page: str, corpus: str | None = None):
    con = db()
    row = _resolve_doc(doc_id, corpus)
    r = con.execute(
        "SELECT body FROM pages WHERE corpus = ? AND doc_id = ? AND page = ?",
        (row["corpus"], row["doc_id"], str(page)),
    ).fetchone()
    if not r:
        raise HTTPException(404, f"no text for {row['doc_id']} page {page}")
    return {
        "corpus": row["corpus"],
        "doc_id": row["doc_id"],
        "title": row["title"],
        "page": page,
        "body": r["body"],
    }


@app.get("/")
def index():
    page = WEB_DIR / "index.html"
    if not page.exists():
        raise HTTPException(404, "UI not installed")
    return FileResponse(page)
