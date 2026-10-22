#!/usr/bin/env bash
# Render deploy/Caddyfile.template into /etc/caddy/Caddyfile and restart caddy.
#
# The rendered file holds two secrets -- the unlock token and the upstream
# Basic credentials -- which is why only the template is in git. Run as root.
#
#   sudo ./deploy/render_caddyfile.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$HERE/.env"
TEMPLATE="$HERE/deploy/Caddyfile.template"
TARGET=/etc/caddy/Caddyfile

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE" >&2; exit 1; }
[ -f "$TEMPLATE" ] || { echo "missing $TEMPLATE" >&2; exit 1; }
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
: "${AUTH_USER:?AUTH_USER not set}" "${AUTH_PASS:?AUTH_PASS not set}" "${ACCESS_TOKEN:?ACCESS_TOKEN not set}"

BASIC=$(printf '%s:%s' "$AUTH_USER" "$AUTH_PASS" | base64 -w0)

# Landing page carries the unlock link, so it is rendered from the same token.
install -d -m 755 /etc/caddy/landing
sed "s|__TOKEN__|$ACCESS_TOKEN|g" "$HERE/deploy/landing.html" > /etc/caddy/landing/index.html
chmod 644 /etc/caddy/landing/index.html

tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
sed -e "s|__TOKEN__|$ACCESS_TOKEN|g" -e "s|__BASIC__|$BASIC|g" "$TEMPLATE" > "$tmp"
caddy validate --adapter caddyfile --config "$tmp" >/dev/null
install -m 640 -o root -g caddy "$tmp" "$TARGET" 2>/dev/null || install -m 600 "$tmp" "$TARGET"
systemctl restart caddy
sleep 2
systemctl is-active --quiet caddy && echo "caddy restarted, config rendered to $TARGET" \
  || { echo "caddy failed to start; see: journalctl -u caddy -n 30" >&2; exit 1; }
echo
echo "Unlock link (bookmark it, open once):"
echo "  https://47.250.10.235:5000/unlock/$ACCESS_TOKEN"
