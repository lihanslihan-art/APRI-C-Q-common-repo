#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Corpus search CLI for the agent. Copied into every run directory as corpus.py.

Why this exists instead of telling the agent to run curl: the agent session's
Bash allowlist matches on the command prefix, so `curl ...` is allowed but
`echo $X && curl ...` or a heredoc wrapping curl is not. The first integration
run was denied on exactly that and fell back to hand-rolled python that
misused the API. A single entry point the allowlist matches cleanly
(`python3 corpus.py ...`) removes the whole class of problem, and lets the
right defaults live in code rather than in prose the agent may skim.

Stdlib only. Reads CORPUS_API and CORPUS_AUTH from the environment.

    python3 corpus.py check
    python3 corpus.py search "non-primary channel access" --mode phrase
    python3 corpus.py search npca --kind cr --ballot LB291
    python3 corpus.py doc 11-24-0209-19
    python3 corpus.py page 11-24-0209-19 12
    python3 corpus.py facets
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("CORPUS_API", "http://127.0.0.1:3014").rstrip("/")
AUTH = os.environ.get("CORPUS_AUTH", "")

# Two corpora with different coverage, and mixing them up is the easy mistake:
#   ieee_standards  published IEEE 802 standards (Wi-Fi 7 and earlier)
#   wifi8_tgbn      the Wi-Fi 8 / 802.11bn working-group record
# A Wi-Fi 8 term like NPCA, MAPC or Co-TDMA appears ONLY in wifi8_tgbn.
CORPORA = ("ieee_standards", "wifi8_tgbn")


def _request(path: str, params: dict | None = None) -> dict:
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    req = urllib.request.Request(url)
    if AUTH:
        req.add_header("Authorization", "Basic " + base64.b64encode(AUTH.encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"corpus API error {e.code} on {path}: {body}")
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise SystemExit(
            f"corpus API unreachable at {API}: {e}\n"
            "Do NOT substitute your own recollection for corpus results. "
            "Report the corpus as unavailable and say the prior-art gate could not run."
        )


def cmd_check(args) -> int:
    """Prove the corpus is actually usable before relying on it."""
    health = _request("/healthz")
    stats = _request("/api/stats")
    probe = _request("/api/search", {"q": "npca", "limit": 1})
    ok = bool(health.get("ok")) and probe.get("total", 0) > 0
    print(f"api         : {API}")
    print(f"health      : {health.get('ok')}")
    print(f"documents   : {stats.get('documents'):,}   pages: {stats.get('pages'):,}")
    for c in stats.get("per_corpus", []):
        print(f"  {c['corpus']:16} {c['documents']:>5} docs  {c['pages']:>6} pages")
    print(f"probe 'npca': {probe.get('total')} hits  (expected > 0)")
    print(f"USABLE      : {ok}")
    if not ok:
        print("\nThe corpus is NOT usable. Say so in the report and do not "
              "substitute your own recollection for retrieval.", file=sys.stderr)
    return 0 if ok else 1


def cmd_search(args) -> int:
    words = args.query.split()
    if args.mode == "token" and len(words) > 1:
        print(f"note: token mode ANDs all {len(words)} words, which often yields 0 hits.\n"
              f"      For a multi-word expression use --mode phrase.\n", file=sys.stderr)
    if args.corpus:
        print(f"note: restricted to {args.corpus}. Wi-Fi 8 / 802.11bn terms "
              f"(NPCA, MAPC, Co-TDMA, DSO, ELR...) exist only in wifi8_tgbn.\n",
              file=sys.stderr)

    d = _request("/api/search", {
        "q": args.query, "mode": args.mode, "corpus": args.corpus,
        "kind": args.kind, "topic": args.topic, "ballot": args.ballot,
        "year": args.year, "limit": args.limit,
    })
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0

    cap = "+" if d.get("total_capped") else ""
    print(f"{d['total']}{cap} hits in {d['took_ms']} ms   MATCH {d['match']}")
    if not d["results"]:
        print("\nno hits. Try --mode phrase for an expression, --mode prefix for a "
              "word stem, or drop --corpus to search both corpora.")
        return 0
    print()
    for r in d["results"]:
        bits = [r["doc_id"]]
        if r.get("kind"):
            bits.append(r["kind"])
        if r.get("ballot"):
            bits.append(r["ballot"])
        bits.append(f"p.{r['page']}")
        # first_disclosed is the r0 date: the only valid prior-art cutoff.
        bits.append(f"first_disclosed={r.get('first_disclosed') or '?'}")
        print("  " + "  ".join(bits))
        print(f"    {(r.get('title') or '')[:110]}")
        print(f"    {(r.get('snippet') or '').replace(chr(10), ' ')[:200]}")
        if r.get("url"):
            print(f"    {r['url']}")
        print()
    return 0


def cmd_doc(args) -> int:
    d = _request(f"/api/doc/{urllib.parse.quote(args.doc_id)}",
                 {"corpus": args.corpus} if args.corpus else None)
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0
    print(f"{d['doc_id']}  [{d.get('kind')}]  {d.get('title')}")
    for k in ("corpus", "ballot", "year", "author", "first_disclosed", "family", "url"):
        if d.get(k):
            print(f"  {k:16} {d[k]}")
    print(f"  pages with text  {len(d.get('pages_with_text') or [])}")
    if d.get("topics"):
        print("  topics           " + ", ".join(t["topic"] for t in d["topics"]))
    if d.get("scope"):
        print(f"  scope            {d['scope'][:300]}")
    toc = d.get("toc") or []
    if toc:
        print(f"\n  table of contents ({len(toc)} entries):")
        for t in toc[: args.toc]:
            print(f"    p.{str(t.get('page') or '?'):>4}  {'  ' * max(0, (t.get('level') or 1) - 1)}{t.get('title')}")
        if len(toc) > args.toc:
            print(f"    ... {len(toc) - args.toc} more (raise --toc)")
    return 0


def cmd_page(args) -> int:
    d = _request(f"/api/doc/{urllib.parse.quote(args.doc_id)}/page/{urllib.parse.quote(args.page)}",
                 {"corpus": args.corpus} if args.corpus else None)
    print(f"=== {d['doc_id']} page {d['page']} — {d.get('title')} ===\n")
    print(d["body"])
    return 0


def cmd_facets(args) -> int:
    d = _request("/api/facets", {"corpus": args.corpus} if args.corpus else None)
    for group in ("corpus", "kind", "ballot", "year", "topic"):
        vals = d.get(group) or []
        if not vals:
            continue
        shown = vals[: args.limit]
        print(f"{group} ({len(vals)}):")
        print("  " + ", ".join(f"{v['value']}({v['count']})" for v in shown))
        if len(vals) > len(shown):
            print(f"  ... {len(vals) - len(shown)} more")
        print()
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="verify the corpus is reachable and returns hits")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("search", help="full-text search (both corpora by default)")
    s.add_argument("query")
    s.add_argument("--mode", default="token",
                   choices=["token", "phrase", "boolean", "prefix"],
                   help="token ANDs every word; phrase matches an exact expression")
    s.add_argument("--corpus", choices=CORPORA, default=None,
                   help="omit to search BOTH; Wi-Fi 8 terms live only in wifi8_tgbn")
    s.add_argument("--kind")
    s.add_argument("--topic")
    s.add_argument("--ballot")
    s.add_argument("--year")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_search)

    d = sub.add_parser("doc", help="document metadata, topics and table of contents")
    d.add_argument("doc_id")
    d.add_argument("--corpus", choices=CORPORA, default=None)
    d.add_argument("--toc", type=int, default=40)
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_doc)

    p = sub.add_parser("page", help="full text of one page")
    p.add_argument("doc_id")
    p.add_argument("page")
    p.add_argument("--corpus", choices=CORPORA, default=None)
    p.set_defaults(func=cmd_page)

    f = sub.add_parser("facets", help="available kind / topic / ballot / year values")
    f.add_argument("--corpus", choices=CORPORA, default=None)
    f.add_argument("--limit", type=int, default=40)
    f.set_defaults(func=cmd_facets)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
