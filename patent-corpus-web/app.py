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

import base64
import binascii
import hmac
import html
import json
import os
import sqlite3
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

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

# --------------------------------------------------------------------------
# HTTP Basic auth
#
# This service is reachable from the public internet, so everything except the
# health probe sits behind auth. The check runs as middleware rather than as a
# route dependency so that no path can be added later and accidentally left
# open, including /docs, /openapi.json and the static UI.
# --------------------------------------------------------------------------

AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_PASS = os.environ.get("AUTH_PASS", "")
ALLOW_NO_AUTH = os.environ.get("ALLOW_NO_AUTH", "") == "1"
REALM = "Patent Corpus Search"

# Only the liveness probe is open: it reveals nothing but a boolean.
PUBLIC_PATHS = {"/healthz"}

# A public Basic-auth endpoint gets scanned. Throttling failed attempts keeps
# brute force, log spam and password-hash CPU burn bounded.
FAIL_LIMIT = 10
FAIL_WINDOW = 300.0
_fails: dict[str, list[float]] = defaultdict(list)
_fails_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    # No reverse proxy in front of this deployment, so the peer address is the
    # real client. If one is added later, trust its header explicitly here
    # rather than believing X-Forwarded-For by default.
    return request.client.host if request.client else "unknown"


def _record_failure(ip: str) -> int:
    now = time.monotonic()
    with _fails_lock:
        hits = [t for t in _fails[ip] if now - t < FAIL_WINDOW]
        hits.append(now)
        _fails[ip] = hits
        return len(hits)


def _is_throttled(ip: str) -> bool:
    now = time.monotonic()
    with _fails_lock:
        hits = [t for t in _fails[ip] if now - t < FAIL_WINDOW]
        _fails[ip] = hits
        return len(hits) >= FAIL_LIMIT


def _credentials_ok(header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    user, _, password = raw.partition(":")
    # Compare both halves in constant time, and always compare both so the
    # timing does not reveal whether the username matched.
    ok_user = hmac.compare_digest(user, AUTH_USER)
    ok_pass = hmac.compare_digest(password, AUTH_PASS)
    return ok_user and ok_pass


def _unauthorized(detail: str = "authentication required") -> Response:
    return JSONResponse(
        {"detail": detail},
        status_code=401,
        headers={"WWW-Authenticate": f'Basic realm="{REALM}", charset="UTF-8"'},
    )


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
    # Refuse to start unauthenticated unless that is asked for explicitly.
    # The service is exposed publicly, so an empty password must be a loud
    # failure rather than a silently open endpoint.
    if not (AUTH_USER and AUTH_PASS) and not ALLOW_NO_AUTH:
        raise RuntimeError(
            "AUTH_USER and AUTH_PASS must be set (see .env.example). "
            "To run without auth on a trusted network, set ALLOW_NO_AUTH=1."
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


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    if ALLOW_NO_AUTH and not (AUTH_USER and AUTH_PASS):
        return await call_next(request)
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    ip = _client_ip(request)
    if _is_throttled(ip):
        return JSONResponse(
            {"detail": "too many failed attempts, try again later"},
            status_code=429,
            headers={"Retry-After": str(int(FAIL_WINDOW))},
        )

    header = request.headers.get("authorization", "")
    if not header:
        return _unauthorized()
    if not _credentials_ok(header):
        n = _record_failure(ip)
        return _unauthorized(f"invalid credentials ({n}/{FAIL_LIMIT})")

    return await call_next(request)


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
