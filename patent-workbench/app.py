#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patent drafting workbench.

A web front end for the upstream Claude Code drafting skill. Submit an idea,
a headless agent session runs the skill's own prior-art gate and pre-drafting
analysis, you approve or reject at the skill's own human gate, and on approval
the same session drafts the deliverables.

Loopback only, on purpose: this service spawns agent sessions that can run an
interpreter and write files, so an HTTP endpoint that triggers one must not be
reachable from the internet. Reach it over an SSH tunnel. See the README.

Run:
    uvicorn app:app --host 127.0.0.1 --port 3015
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import json
import os
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

import jobs
import runner
from jobs import store

BASE = Path(__file__).resolve().parent
WEB_DIR = BASE / "web"

# --------------------------------------------------------------------------
# HTTP Basic auth. Same contract as the corpus service: middleware rather than
# a route dependency, so a path added later cannot be left open by accident.
# Deliberately duplicated instead of shared — two independently deployable
# services should not fail together over a common import.
# --------------------------------------------------------------------------

AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_PASS = os.environ.get("AUTH_PASS", "")
ALLOW_NO_AUTH = os.environ.get("ALLOW_NO_AUTH", "") == "1"
REALM = "Patent Workbench"
PUBLIC_PATHS = {"/healthz"}

FAIL_LIMIT = 10
FAIL_WINDOW = 300.0
_fails: dict[str, list[float]] = defaultdict(list)
_fails_lock = threading.Lock()


def _client_ip(request: Request) -> str:
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
    ok_user = hmac.compare_digest(user, AUTH_USER)
    ok_pass = hmac.compare_digest(password, AUTH_PASS)
    return ok_user and ok_pass


def _unauthorized(detail: str = "authentication required") -> Response:
    return JSONResponse(
        {"detail": detail}, status_code=401,
        headers={"WWW-Authenticate": f'Basic realm="{REALM}", charset="UTF-8"'},
    )


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not (AUTH_USER and AUTH_PASS) and not ALLOW_NO_AUTH:
        raise RuntimeError(
            "AUTH_USER and AUTH_PASS must be set (see .env.example). "
            "To run without auth on a trusted network, set ALLOW_NO_AUTH=1."
        )
    if not runner.SKILLS_SRC.is_dir():
        raise RuntimeError(f"upstream skills not found at {runner.SKILLS_SRC}")
    if not Path(runner.CLAUDE_BIN).exists():
        raise RuntimeError(f"claude CLI not found at {runner.CLAUDE_BIN}")

    # A job that was mid-run when the service stopped has no process behind it
    # any more. Fail it explicitly rather than leaving a row that claims to be
    # running forever. Its agent session still exists, so a screening job can
    # be approved later and resumed.
    orphans = [j for j in store.list(limit=500) if j["status"] in jobs.ACTIVE]
    for j in orphans:
        if j["status"] == jobs.SCREENING and j.get("session_id"):
            store.set_status(j["id"], jobs.AWAITING_APPROVAL,
                             screen_summary=(j.get("screen_summary") or "")
                             + "\n\n[服务在筛查过程中重启，本阶段未正常结束；"
                               "会话仍可恢复，可直接批准继续，或取消后重新提交。]")
        else:
            store.set_status(j["id"], jobs.FAILED,
                             error="service restarted while this phase was running")

    # Anything still queued never got a worker; start them now.
    for j in store.list(limit=500, status=jobs.QUEUED):
        asyncio.create_task(runner.run_screen(j["id"]))

    yield


app = FastAPI(title="Patent Drafting Workbench", version="1.0.0", lifespan=lifespan)


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
            status_code=429, headers={"Retry-After": str(int(FAIL_WINDOW))},
        )
    header = request.headers.get("authorization", "")
    if not header:
        return _unauthorized()
    if not _credentials_ok(header):
        n = _record_failure(ip)
        return _unauthorized(f"invalid credentials ({n}/{FAIL_LIMIT})")
    return await call_next(request)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/slots")
def slots():
    s = runner.slots()
    s["model"] = runner.MODEL
    s["budget_screen_usd"] = runner.BUDGET_SCREEN
    s["budget_draft_usd"] = runner.BUDGET_DRAFT
    s["corpus_api"] = runner.CORPUS_API
    s["corpus_api_reachable"] = _corpus_reachable()
    return s


def _corpus_reachable() -> bool:
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(runner.CORPUS_API + "/healthz", timeout=2) as r:
            return json.load(r).get("ok") is True
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return False


@app.post("/api/jobs", status_code=201)
async def create_job(
    title: str = Body(..., min_length=1, max_length=200),
    idea: str = Body(..., min_length=30, max_length=40_000),
    track: str = Body("std"),
):
    if track not in ("std", "product", "generic"):
        raise HTTPException(400, "track must be std, product or generic")
    job_id = store.create(title.strip(), idea.strip(), track)
    asyncio.create_task(runner.run_screen(job_id))
    return {"id": job_id, "status": jobs.QUEUED}


@app.get("/api/jobs")
def list_jobs(limit: int = Query(50, ge=1, le=200), status: str | None = None):
    rows = store.list(limit=limit, status=status)
    for r in rows:
        r.pop("idea", None)  # keep the list payload small
    return {"jobs": rows, "slots": runner.slots()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    job["artifacts"] = store.artifacts(job_id)
    job["event_count"] = len(store.read_events(job_id))
    return job


@app.get("/api/jobs/{job_id}/events")
def get_events(job_id: str, since: int = Query(0, ge=0)):
    if not store.get(job_id):
        raise HTTPException(404, "no such job")
    raw = store.read_events(job_id, since=since)
    distilled = [e for e in (runner._distill(r) for r in raw if "_meta" not in r) if e]
    return {"since": since, "count": len(raw), "events": distilled}


@app.get("/api/jobs/{job_id}/stream")
async def stream(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")

    async def gen():
        # Replay history first so a reconnecting browser is never missing
        # anything, then follow live.
        for r in store.read_events(job_id):
            if "_meta" in r:
                continue
            ev = runner._distill(r)
            if ev:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        cur = store.get(job_id)
        yield f"data: {json.dumps({'kind': 'status', 'status': cur['status']}, ensure_ascii=False)}\n\n"
        if cur["status"] in jobs.TERMINAL:
            yield "event: close\ndata: {}\n\n"
            return

        q = runner.subscribe(job_id)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    cur = store.get(job_id)
                    if cur and cur["status"] in jobs.TERMINAL:
                        yield f"data: {json.dumps({'kind': 'status', 'status': cur['status']}, ensure_ascii=False)}\n\n"
                        yield "event: close\ndata: {}\n\n"
                        return
                    continue
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev.get("kind") in ("done", "failed", "awaiting_approval"):
                    cur = store.get(job_id)
                    yield f"data: {json.dumps({'kind': 'status', 'status': cur['status']}, ensure_ascii=False)}\n\n"
                    if cur["status"] in jobs.TERMINAL:
                        yield "event: close\ndata: {}\n\n"
                        return
        finally:
            runner.unsubscribe(job_id, q)

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.post("/api/jobs/{job_id}/approve")
async def approve(job_id: str, note: str = Body("", embed=True, max_length=4000)):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if job["status"] != jobs.AWAITING_APPROVAL:
        raise HTTPException(409, f"job is {job['status']}, not {jobs.AWAITING_APPROVAL}")
    asyncio.create_task(runner.run_draft(job_id, note))
    return {"id": job_id, "status": "drafting scheduled"}


@app.post("/api/jobs/{job_id}/reject")
def reject(job_id: str, note: str = Body("", embed=True, max_length=4000)):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if job["status"] != jobs.AWAITING_APPROVAL:
        raise HTTPException(409, f"job is {job['status']}, not {jobs.AWAITING_APPROVAL}")
    store.set_status(job_id, jobs.REJECTED, error=note or None)
    return {"id": job_id, "status": jobs.REJECTED}


@app.post("/api/jobs/{job_id}/cancel")
async def cancel(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if job["status"] in jobs.TERMINAL:
        raise HTTPException(409, f"job is already {job['status']}")
    killed = await runner.cancel(job_id)
    return {"id": job_id, "status": jobs.CANCELLED, "process_killed": killed}


@app.get("/api/jobs/{job_id}/artifacts")
def artifacts(job_id: str):
    if not store.get(job_id):
        raise HTTPException(404, "no such job")
    return {"artifacts": store.artifacts(job_id)}


@app.get("/api/jobs/{job_id}/artifacts/{path:path}")
def artifact(job_id: str, path: str):
    if not store.get(job_id):
        raise HTTPException(404, "no such job")
    root = store.output_dir(job_id).resolve()
    try:
        target = (root / path).resolve()
    except (OSError, RuntimeError):
        raise HTTPException(400, "bad path")
    # Containment check: a crafted path must not escape the output directory.
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(404, "no such artifact")
    return FileResponse(target, filename=target.name)


@app.get("/")
def index():
    page = WEB_DIR / "index.html"
    if not page.exists():
        raise HTTPException(404, "UI not installed")
    return FileResponse(page)
