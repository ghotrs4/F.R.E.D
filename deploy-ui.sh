#!/usr/bin/env bash
set -euo pipefail

# One-command UI deployment for EC2 + nginx static hosting.
# Usage:
#   ./deploy-ui.sh
#   ./deploy-ui.sh fredfridge.duckdns.org

DOMAIN="${1:-fredfridge.duckdns.org}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
UI_DIR="$REPO_ROOT/UI"

if [[ ! -d "$UI_DIR" ]]; then
  echo "[error] UI directory not found: $UI_DIR"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[error] npm is not installed"
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "[error] rsync is not installed"
  exit 1
fi

echo "[1/6] Building UI in $UI_DIR"
cd "$UI_DIR"
npm ci
npm run build

if [[ ! -d "$UI_DIR/dist" ]]; then
  echo "[error] Build completed but dist/ is missing"
  exit 1
fi

echo "[2/6] Verifying build contains expected MQ update hooks"
if ! grep -q '/api/sensor/mq/config' "$UI_DIR"/dist/assets/index-*.js; then
  echo "[warn] Built bundle does not contain /api/sensor/mq/config"
fi
if ! grep -q 'mq-calibration-complete' "$UI_DIR"/dist/assets/index-*.js; then
  echo "[warn] Built bundle does not contain mq-calibration-complete"
fi

echo "[3/6] Detecting nginx web root for domain: $DOMAIN"
WEBROOT="$(sudo nginx -T 2>/dev/null | awk -v domain="$DOMAIN" '
  $1 == "server_name" && index($0, domain) > 0 { in_server = 1; next }
  in_server && $1 == "root" {
    gsub(";", "", $2)
    print $2
    exit
  }
  in_server && $1 == "}" { in_server = 0 }
')"

if [[ -z "$WEBROOT" ]]; then
  echo "[error] Could not find nginx root for server_name $DOMAIN"
  echo "[hint] Check sudo nginx -T output and ensure this domain has a root directive"
  exit 1
fi

echo "[info] Web root: $WEBROOT"

echo "[4/6] Syncing dist/ to nginx web root"
sudo mkdir -p "$WEBROOT"
sudo rsync -a --delete "$UI_DIR/dist/" "$WEBROOT/"

echo "[5/6] Validating and reloading nginx"
sudo nginx -t
sudo systemctl reload nginx

echo "[6/6] Post-deploy asset check"
ASSET="$(curl -sk "https://$DOMAIN/" | grep -o 'assets/index-[^"]*\.js' | head -n1 || true)"
echo "[info] Served asset: ${ASSET:-<none>}"
if [[ -n "$ASSET" ]]; then
  if curl -sk "https://$DOMAIN/$ASSET" | grep -q '/api/sensor/mq/config'; then
    echo "[ok] Served bundle contains /api/sensor/mq/config"
  else
    echo "[warn] Served bundle missing /api/sensor/mq/config"
  fi
  if curl -sk "https://$DOMAIN/$ASSET" | grep -q 'mq-calibration-complete'; then
    echo "[ok] Served bundle contains mq-calibration-complete"
  else
    echo "[warn] Served bundle missing mq-calibration-complete"
  fi
fi

echo "[done] UI deploy complete"
