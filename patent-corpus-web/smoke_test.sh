#!/usr/bin/env bash
# Smoke test for the corpus search service. Usage: ./smoke_test.sh [base_url]
#
# Credentials come from .env (AUTH_USER / AUTH_PASS) or the environment.
# Run this against a freshly restarted service: the auth throttle counts
# failed attempts per IP, and this test makes some on purpose.
set -uo pipefail
B="${1:-http://127.0.0.1:3014}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] && . "$HERE/.env"
AUTH="${AUTH_USER:-}:${AUTH_PASS:-}"
pass=0; fail=0

check() { # name expected_code url [curl args...]
  local name="$1" want="$2" url="$3"; shift 3
  local got
  got=$(curl -s -o /dev/null -w '%{http_code}' -u "$AUTH" "$@" "$url")
  if [ "$got" = "$want" ]; then printf '  ok    %-42s %s\n' "$name" "$got"; pass=$((pass+1))
  else printf '  FAIL  %-42s got %s want %s\n' "$name" "$got" "$want"; fail=$((fail+1)); fi
}

echo "smoke testing $B"
check "health"                 200 "$B/healthz"
check "stats"                  200 "$B/api/stats"
check "facets"                 200 "$B/api/facets"
check "ui"                     200 "$B/"
check "openapi"                200 "$B/openapi.json"
check "token search"           200 "$B/api/search?q=npca&limit=5"
check "hyphen token"           200 "$B/api/search?q=co-tdma&limit=5"
check "prefix search"          200 "$B/api/search?q=sensi&mode=prefix&limit=5"
check "corpus filter"          200 "$B/api/search?q=beacon&corpus=ieee_standards&limit=5"
check "kind+ballot filter"     200 "$B/api/search?q=npca&kind=cr&ballot=LB291&limit=5"
check "phrase search"          200 "$B/api/search" --get --data-urlencode 'q=non-primary channel access' --data-urlencode 'mode=phrase'
check "boolean search"         200 "$B/api/search" --get --data-urlencode 'q=co-tdma AND rtwt' --data-urlencode 'mode=boolean'
check "doc metadata"           200 "$B/api/doc/11-24-0209-19"
check "doc page"               200 "$B/api/doc/11-24-0209-19/page/12"
check "empty query rejected"   422 "$B/api/search?q="
check "operators-only rejected" 400 "$B/api/search" --get --data-urlencode 'q=AND' --data-urlencode 'mode=boolean'
check "limit over cap"         422 "$B/api/search?q=npca&limit=9999"
check "unknown doc"            404 "$B/api/doc/does-not-exist"
check "page without text"      404 "$B/api/doc/11-24-0209-19/page/99999"

# Auth. Every surface except the health probe must be closed.
printf '  ---- auth ----\n'
for p in / /docs /openapi.json "/api/search?q=npca" /api/facets /api/stats; do
  got=$(curl -s -o /dev/null -w '%{http_code}' "$B$p")
  if [ "$got" = "401" ]; then printf '  ok    %-42s 401\n' "closed: $p"; pass=$((pass+1))
  else printf '  FAIL  %-42s got %s want 401\n' "closed: $p" "$got"; fail=$((fail+1)); fi
done
check "healthz open by design"    200 "$B/healthz"
got=$(curl -s -o /dev/null -w '%{http_code}' -u "${AUTH_USER:-x}:definitely-wrong" "$B/api/stats")
if [ "$got" = "401" ] || [ "$got" = "429" ]; then
  printf '  ok    %-42s %s\n' "wrong password refused" "$got"; pass=$((pass+1))
else printf '  FAIL  %-42s got %s\n' "wrong password refused" "$got"; fail=$((fail+1)); fi

# Content assertions, not just status codes.
printf '  ---- content ----\n'
n=$(curl -s -u "$AUTH" "$B/api/stats" | python3 -c 'import json,sys; print(json.load(sys.stdin)["documents"])')
if [ "$n" -ge 2800 ]; then printf '  ok    %-42s %s docs\n' "corpus fully indexed" "$n"; pass=$((pass+1))
else printf '  FAIL  %-42s only %s docs\n' "corpus fully indexed" "$n"; fail=$((fail+1)); fi

leak=$(curl -s -u "$AUTH" "$B/api/search?q=script&limit=25" | python3 -c '
import json,sys,re
d=json.load(sys.stdin)
bad=[t for r in d["results"] for t in re.findall(r"</?[a-zA-Z][^>]*>", r["snippet_html"]) if t not in ("<mark>","</mark>")]
print(len(bad))')
if [ "$leak" = "0" ]; then printf '  ok    %-42s 0 leaks\n' "snippet html escaped"; pass=$((pass+1))
else printf '  FAIL  %-42s %s unescaped tags\n' "snippet html escaped" "$leak"; fail=$((fail+1)); fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
