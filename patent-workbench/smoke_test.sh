#!/usr/bin/env bash
# Smoke test for the drafting workbench. Usage: ./smoke_test.sh [base_url]
#
# Scope: everything that does NOT spawn an agent session. Submitting a job
# starts a real headless Claude Code run that costs money and takes minutes,
# so it is not part of an automated smoke test. See the README's "what is
# verified" section for how to exercise that path deliberately.
set -uo pipefail
B="${1:-http://127.0.0.1:3015}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] && . "$HERE/.env"
AUTH="${AUTH_USER:-}:${AUTH_PASS:-}"
pass=0; fail=0

check() { # name want url [curl args...]
  local name="$1" want="$2" url="$3"; shift 3
  local got
  got=$(curl -s -o /dev/null -w '%{http_code}' -u "$AUTH" "$@" "$url")
  if [ "$got" = "$want" ]; then printf '  ok    %-42s %s\n' "$name" "$got"; pass=$((pass+1))
  else printf '  FAIL  %-42s got %s want %s\n' "$name" "$got" "$want"; fail=$((fail+1)); fi
}
assert() { # name condition-result detail
  if [ "$2" = "true" ]; then printf '  ok    %-42s %s\n' "$1" "$3"; pass=$((pass+1))
  else printf '  FAIL  %-42s %s\n' "$1" "$3"; fail=$((fail+1)); fi
}

echo "smoke testing $B"
check "health"                 200 "$B/healthz"
check "slots"                  200 "$B/api/slots"
check "job list"               200 "$B/api/jobs"
check "ui"                     200 "$B/"
check "openapi"                200 "$B/openapi.json"
check "unknown job"            404 "$B/api/jobs/does-not-exist"
check "unknown job events"     404 "$B/api/jobs/does-not-exist/events"
check "unknown job artifacts"  404 "$B/api/jobs/does-not-exist/artifacts"
check "approve unknown job"    404 "$B/api/jobs/nope/approve" -X POST -H 'Content-Type: application/json' -d '{"note":""}'
check "cancel unknown job"     404 "$B/api/jobs/nope/cancel" -X POST

printf '  ---- input validation (rejected before any agent starts) ----\n'
check "idea too short"         422 "$B/api/jobs" -X POST -H 'Content-Type: application/json' -d '{"title":"t","idea":"short","track":"std"}'
check "title missing"          422 "$B/api/jobs" -X POST -H 'Content-Type: application/json' -d '{"idea":"0123456789012345678901234567890123456789","track":"std"}'
check "bad track"              400 "$B/api/jobs" -X POST -H 'Content-Type: application/json' -d '{"title":"t","idea":"0123456789012345678901234567890123456789","track":"nope"}'

printf '  ---- auth ----\n'
for p in / /openapi.json /api/slots /api/jobs; do
  got=$(curl -s -o /dev/null -w '%{http_code}' "$B$p")
  if [ "$got" = "401" ]; then printf '  ok    %-42s 401\n' "closed: $p"; pass=$((pass+1))
  else printf '  FAIL  %-42s got %s want 401\n' "closed: $p" "$got"; fail=$((fail+1)); fi
done
check "healthz open by design" 200 "$B/healthz"
got=$(curl -s -o /dev/null -w '%{http_code}' -u "${AUTH_USER:-x}:definitely-wrong" "$B/api/slots")
assert "wrong password refused" "$([ "$got" = 401 ] || [ "$got" = 429 ] && echo true || echo false)" "$got"

printf '  ---- exposure ----\n'
bind=$(ss -ltn 2>/dev/null | grep -c '127.0.0.1:3015')
assert "bound to loopback only" "$([ "$bind" -ge 1 ] && echo true || echo false)" "127.0.0.1:3015"
wild=$(ss -ltn 2>/dev/null | grep -c '0.0.0.0:3015')
assert "not bound to 0.0.0.0" "$([ "$wild" -eq 0 ] && echo true || echo false)" "no wildcard bind"

printf '  ---- wiring ----\n'
reach=$(curl -s -u "$AUTH" "$B/api/slots" | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["corpus_api_reachable"]).lower())')
assert "corpus search service reachable" "$reach" "plan B dependency"
cc=$(curl -s -u "$AUTH" "$B/api/slots" | python3 -c 'import json,sys; print(json.load(sys.stdin)["max_concurrent"])')
assert "concurrency capped at 2" "$([ "$cc" = 2 ] && echo true || echo false)" "max_concurrent=$cc"
deps=$("$HERE/.venv/bin/python" -c '
import importlib
missing=[m for m in ("pptx","docx","matplotlib","fitz") if not importlib.util.find_spec(m)]
print("true" if not missing else "false:"+",".join(missing))' 2>/dev/null)
assert "agent-side builder deps present" "${deps%%:*}" "python-pptx/docx/matplotlib/PyMuPDF"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
