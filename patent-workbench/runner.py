#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runs the upstream drafting skill in a headless Claude Code session.

One job = one agent session, driven in two phases with a human gate between
them (see prompts.py). Phase 2 resumes the same session id, so the prior-art
findings and the pre-drafting analysis stay in context rather than being
re-derived.

Isolation: each job gets its own directory containing a private copy of the
skills and its own output/. The 179 MB reference corpus is symlinked rather
than copied, because it is read-only and copying it per job would cost more
disk than the whole rest of the service.

Concurrency is capped at 2. A headless session measured 283 MB resident and
this host has about 1.2 GB free, so a third concurrent run risks the OOM
killer taking out the other services on the box.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import jobs
import prompts
from jobs import store

BASE = Path(__file__).resolve().parent
VENV_BIN = BASE / ".venv" / "bin"

# Upstream workspace: read-only source of the skills and the reference corpus.
UPSTREAM = Path(os.environ.get("UPSTREAM_ROOT", "/home/admin/ai_patent_experiments"))
SKILLS_SRC = UPSTREAM / ".claude" / "skills"
REFERENCES = SKILLS_SRC / "wifi_patent_skill" / "references"

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/home/admin/.nvm/versions/node/v24.16.0/bin/claude")
MODEL = os.environ.get("AGENT_MODEL", "claude-opus-5")

CORPUS_API = os.environ.get("CORPUS_API", "http://127.0.0.1:3014")
CORPUS_AUTH = os.environ.get("CORPUS_AUTH", "")

BUDGET_SCREEN = float(os.environ.get("BUDGET_SCREEN_USD", "5"))
BUDGET_DRAFT = float(os.environ.get("BUDGET_DRAFT_USD", "20"))

MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))
# A stream-json line carrying a large tool result can be megabytes. asyncio's
# default 64 KB line limit would abort the read, so raise it well past that.
STDOUT_LINE_LIMIT = 16 * 1024 * 1024

# Tool surface for the agent session.
#
# Bash is scoped to the commands the skill actually needs rather than granted
# wholesale: the deliverable builders (python3), the corpus API (curl), and
# basic file shuffling. Read/Write/Edit/Glob/Grep cover the rest of the file
# work without a shell.
#
# Be clear about what this allowlist is worth: it is a speed bump, NOT a
# sandbox. `python3 -c "import os; os.system(...)"` walks straight through it,
# and any allowlist that lets an agent run an interpreter has the same hole.
# The boundaries that actually hold here are:
#
#   1. the service binds to 127.0.0.1, so nothing can trigger a run remotely;
#   2. --permission-prompts none, so anything not listed is denied outright
#      rather than waiting for an answer nobody is there to give;
#   3. --max-budget-usd, a hard ceiling on each phase.
#
# Real isolation means running the agent in a container with only the run
# directory writable and the corpus mounted read-only. That is the next step
# for this service and is written up in the README; until then, do not expose
# this port beyond loopback.
TOOLS_ALLOWED = [
    "Read", "Write", "Edit", "Glob", "Grep", "TodoWrite", "Skill", "NotebookEdit",
    "WebFetch", "WebSearch",
    "Bash(python3 *)", "Bash(python *)", "Bash(curl *)",
    "Bash(mkdir *)", "Bash(cp *)", "Bash(mv *)", "Bash(ls *)", "Bash(cat *)",
]
# Belt and braces on top of the scoped allowlist above.
TOOLS_DENIED = [
    "Bash(git *)", "Bash(gh *)", "Bash(sudo *)", "Bash(systemctl *)",
    "Bash(ssh *)", "Bash(scp *)", "Bash(rm *)", "Bash(chmod *)", "Bash(pip *)",
]

_sem = asyncio.Semaphore(MAX_CONCURRENT)
_subscribers: dict[str, set[asyncio.Queue]] = {}
_procs: dict[str, asyncio.subprocess.Process] = {}


# --------------------------------------------------------------------------
# Event fan-out
# --------------------------------------------------------------------------

def subscribe(job_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _subscribers.setdefault(job_id, set()).add(q)
    return q


def unsubscribe(job_id: str, q: asyncio.Queue) -> None:
    subs = _subscribers.get(job_id)
    if subs:
        subs.discard(q)
        if not subs:
            _subscribers.pop(job_id, None)


def _publish(job_id: str, event: dict) -> None:
    for q in list(_subscribers.get(job_id, ())):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            # A browser that cannot keep up loses live events, not history:
            # everything is still on disk and replayed when it reconnects.
            pass


# --------------------------------------------------------------------------
# Run directory
# --------------------------------------------------------------------------

def _ignore_references(dirname: str, names: list[str]) -> set[str]:
    if Path(dirname).name == "wifi_patent_skill":
        return {"references"}
    return set()


def prepare_run_dir(job_id: str, title: str, idea: str, track: str) -> Path:
    """Private skill copy + symlinked corpus + empty output/."""
    run = store.run_dir(job_id)
    (run / "output").mkdir(parents=True, exist_ok=True)

    skills_dst = run / ".claude" / "skills"
    if not skills_dst.exists():
        skills_dst.parent.mkdir(parents=True, exist_ok=True)
        # Copy everything but the reference corpus: the copy is what makes the
        # job unable to mutate the shared skills.
        shutil.copytree(SKILLS_SRC, skills_dst, ignore=_ignore_references,
                        symlinks=True, ignore_dangling_symlinks=True)
        link = skills_dst / "wifi_patent_skill" / "references"
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.exists():
            link.symlink_to(REFERENCES, target_is_directory=True)

    # The corpus CLI the agent must use for prior art. A single entry point
    # the Bash allowlist matches cleanly beats telling the agent to compose
    # curl commands, which the allowlist rejects the moment anything is
    # piped or wrapped in a heredoc.
    shutil.copyfile(BASE / "corpus_cli.py", run / "corpus.py")

    # The submitted idea, on disk, so a run is reproducible from its directory
    # alone without consulting the job database.
    (run / "idea_brief.md").write_text(
        f"# {title}\n\n- job: {job_id}\n- track: {track}\n"
        f"- submitted: {time.strftime('%Y-%m-%d %H:%M:%S%z')}\n\n## 想法描述\n\n{idea}\n",
        encoding="utf-8",
    )
    return run


def _env() -> dict[str, str]:
    env = dict(os.environ)
    # python3 must resolve to the venv that has python-pptx / python-docx /
    # matplotlib / PyMuPDF, or the skill's builders cannot run.
    env["PATH"] = f"{VENV_BIN}:{env.get('PATH', '')}"
    env["CORPUS_API"] = CORPUS_API
    env["CORPUS_AUTH"] = CORPUS_AUTH
    # Keep the agent's own output stable and machine-readable.
    env["CLAUDE_CODE_NONINTERACTIVE"] = "1"
    return env


# --------------------------------------------------------------------------
# Phase execution
# --------------------------------------------------------------------------

def _distill(raw: dict) -> dict | None:
    """Turn a stream-json event into something worth showing a person."""
    t = raw.get("type")
    ts = time.time()

    if t == "system" and raw.get("subtype") == "init":
        return {"kind": "init", "ts": ts, "session_id": raw.get("session_id"),
                "model": raw.get("model"), "tools": len(raw.get("tools") or [])}

    if t == "assistant":
        blocks = (raw.get("message") or {}).get("content") or []
        for b in blocks:
            if b.get("type") == "text" and b.get("text", "").strip():
                return {"kind": "text", "ts": ts, "text": b["text"]}
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                detail = (
                    inp.get("command") or inp.get("file_path") or inp.get("pattern")
                    or inp.get("url") or inp.get("query") or inp.get("skill") or ""
                )
                return {"kind": "tool", "ts": ts, "name": b.get("name"),
                        "detail": str(detail)[:300]}
            if b.get("type") == "thinking":
                return {"kind": "thinking", "ts": ts}
        return None

    if t == "user":
        blocks = (raw.get("message") or {}).get("content") or []
        for b in blocks:
            if b.get("type") == "tool_result":
                content = b.get("content")
                if isinstance(content, list):
                    text = " ".join(
                        x.get("text", "") for x in content if isinstance(x, dict)
                    )
                else:
                    text = str(content or "")
                return {"kind": "tool_result", "ts": ts,
                        "is_error": bool(b.get("is_error")),
                        "preview": text[:300]}
        return None

    if t == "result":
        return {"kind": "result", "ts": ts, "subtype": raw.get("subtype"),
                "cost_usd": raw.get("total_cost_usd"), "turns": raw.get("num_turns"),
                "duration_ms": raw.get("duration_ms"),
                "is_error": bool(raw.get("is_error")),
                "text": raw.get("result") or ""}

    if t == "rate_limit_event":
        return None

    return {"kind": t or "unknown", "ts": ts}


async def _run_claude(job_id: str, prompt: str, budget: float,
                      resume: str | None) -> dict:
    """Spawn one headless session, stream it, and return the result summary."""
    run = store.run_dir(job_id)
    cmd = [
        CLAUDE_BIN, "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--model", MODEL,
        "--permission-mode", "acceptEdits",
        "--permission-prompts", "none",
        "--max-budget-usd", str(budget),
        "--allowedTools", *TOOLS_ALLOWED,
        "--disallowedTools", *TOOLS_DENIED,
        "--add-dir", str(REFERENCES.resolve()),
    ]
    if resume:
        cmd += ["--resume", resume]

    store.append_event(job_id, {"_meta": "spawn", "ts": time.time(),
                                "resume": resume, "budget": budget,
                                "model": MODEL})
    _publish(job_id, {"kind": "phase_start", "ts": time.time(),
                      "resume": bool(resume), "budget": budget})

    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(run), env=_env(),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        limit=STDOUT_LINE_LIMIT,
    )
    _procs[job_id] = proc

    summary: dict[str, Any] = {"session_id": resume, "cost_usd": 0.0,
                               "turns": 0, "text": "", "error": None}

    async def pump_stdout():
        assert proc.stdout
        while True:
            try:
                line = await proc.stdout.readline()
            except (asyncio.LimitOverrunError, ValueError) as e:
                store.append_event(job_id, {"_meta": "stdout_overrun", "error": str(e)})
                continue
            if not line:
                break
            s = line.decode("utf-8", errors="replace").strip()
            if not s:
                continue
            try:
                raw = json.loads(s)
            except json.JSONDecodeError:
                store.append_event(job_id, {"_meta": "unparsed", "line": s[:2000]})
                continue
            store.append_event(job_id, raw)

            if raw.get("session_id") and not summary["session_id"]:
                summary["session_id"] = raw["session_id"]
                store.update(job_id, session_id=raw["session_id"])
            if raw.get("type") == "result":
                summary["cost_usd"] = raw.get("total_cost_usd") or 0.0
                summary["turns"] = raw.get("num_turns") or 0
                summary["text"] = raw.get("result") or ""
                if raw.get("is_error") or raw.get("subtype") != "success":
                    summary["error"] = f"agent result: {raw.get('subtype')}"

            ev = _distill(raw)
            if ev:
                _publish(job_id, ev)

    async def pump_stderr():
        assert proc.stderr
        chunks = []
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            chunks.append(line.decode("utf-8", errors="replace"))
        if chunks:
            err = "".join(chunks)
            (run / "stderr.log").write_text(err, encoding="utf-8")
            store.append_event(job_id, {"_meta": "stderr", "text": err[:4000]})

    await asyncio.gather(pump_stdout(), pump_stderr())
    rc = await proc.wait()
    _procs.pop(job_id, None)

    store.add_cost(job_id, summary["cost_usd"], summary["turns"])
    if rc != 0 and not summary["error"]:
        summary["error"] = f"claude exited {rc}"
    store.append_event(job_id, {"_meta": "exit", "ts": time.time(), "rc": rc})
    return summary


# --------------------------------------------------------------------------
# Phases
# --------------------------------------------------------------------------

def corpus_usable() -> tuple[bool, str]:
    """Is the prior-art corpus actually answering queries?

    The first integration run produced a prior-art report with no corpus
    citations at all, because every query came back empty and the agent fell
    back on its own recollection. A screening run without retrieval is worse
    than no screening: it reads as evidence but is not. So this is checked
    before the session is spawned, not discovered afterwards.
    """
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(
            CORPUS_API + "/api/search?q=npca&limit=1")
        if CORPUS_AUTH:
            req.add_header(
                "Authorization",
                "Basic " + base64.b64encode(CORPUS_AUTH.encode()).decode())
        with urllib.request.urlopen(req, timeout=10) as r:
            total = json.load(r).get("total", 0)
        if total > 0:
            return True, f"corpus answering ({total} hits for the probe query)"
        return False, "corpus reachable but the probe query returned 0 hits"
    except urllib.error.HTTPError as e:
        return False, f"corpus API returned HTTP {e.code} (check CORPUS_AUTH)"
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as e:
        return False, f"corpus API unreachable at {CORPUS_API}: {e}"


def _settle(job_id: str, status: str, **extra) -> bool:
    """Set a terminal status unless the job was deliberately cancelled.

    Cancelling kills the agent process, which makes it exit non-zero, which
    used to land the job in `failed` and hide the fact that a person stopped
    it on purpose. A cancellation is the final word.
    """
    cur = store.get(job_id)
    if cur and cur["status"] == jobs.CANCELLED:
        return False
    store.set_status(job_id, status, **extra)
    return True


async def run_screen(job_id: str) -> None:
    job = store.get(job_id)
    if not job:
        return
    async with _sem:
        if store.get(job_id)["status"] == jobs.CANCELLED:
            return
        ok, why = corpus_usable()
        if not ok:
            store.set_status(job_id, jobs.FAILED,
                             error=f"prior-art corpus unusable: {why}. "
                                   "Screening without retrieval would produce a "
                                   "report that looks like evidence and is not.")
            _publish(job_id, {"kind": "failed", "ts": time.time(), "error": why})
            return
        store.set_status(job_id, jobs.SCREENING)
        prepare_run_dir(job_id, job["title"], job["idea"], job["track"])
        try:
            r = await _run_claude(
                job_id,
                prompts.screen_prompt(job["title"], job["idea"], job["track"]),
                BUDGET_SCREEN, resume=None,
            )
        except Exception as e:  # spawn failure, disk full, killed process
            if _settle(job_id, jobs.FAILED, error=f"{type(e).__name__}: {e}"):
                _publish(job_id, {"kind": "failed", "ts": time.time(), "error": str(e)})
            return

    if r["error"]:
        if _settle(job_id, jobs.FAILED, error=r["error"]):
            _publish(job_id, {"kind": "failed", "ts": time.time(), "error": r["error"]})
        return

    if _settle(job_id, jobs.AWAITING_APPROVAL, screen_summary=r["text"][:4000]):
        _publish(job_id, {"kind": "awaiting_approval", "ts": time.time(),
                          "summary": r["text"]})


async def run_draft(job_id: str, note: str) -> None:
    job = store.get(job_id)
    if not job or not job.get("session_id"):
        store.set_status(job_id, jobs.FAILED,
                         error="no agent session to resume; re-run the screening phase")
        return
    async with _sem:
        if store.get(job_id)["status"] == jobs.CANCELLED:
            return
        store.set_status(job_id, jobs.DRAFTING)
        try:
            r = await _run_claude(job_id, prompts.draft_prompt(note),
                                  BUDGET_DRAFT, resume=job["session_id"])
        except Exception as e:
            if _settle(job_id, jobs.FAILED, error=f"{type(e).__name__}: {e}"):
                _publish(job_id, {"kind": "failed", "ts": time.time(), "error": str(e)})
            return

    if r["error"]:
        if _settle(job_id, jobs.FAILED, error=r["error"]):
            _publish(job_id, {"kind": "failed", "ts": time.time(), "error": r["error"]})
        return

    if _settle(job_id, jobs.DONE):
        _publish(job_id, {"kind": "done", "ts": time.time(), "text": r["text"],
                          "artifacts": store.artifacts(job_id)})


async def cancel(job_id: str) -> bool:
    proc = _procs.get(job_id)
    store.set_status(job_id, jobs.CANCELLED)
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
        return True
    return False


def slots() -> dict:
    return {"max_concurrent": MAX_CONCURRENT,
            "active": store.count_active(),
            "queued": len(store.list(limit=200, status=jobs.QUEUED))}
