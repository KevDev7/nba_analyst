#!/usr/bin/env bash
set -euo pipefail

if ! command -v portless >/dev/null 2>&1; then
  echo "Portless is not installed."
  echo "Install it with: npm install -g portless"
  exit 1
fi

if pgrep -f "portless proxy start.*--port 1355" >/dev/null 2>&1; then
  echo "Stopping Portless fallback proxy on 1355 so clean HTTPS URLs can use port 443..."
  portless proxy stop -p 1355
fi

portless proxy start --https

if pgrep -f "portless proxy start.*--port 1355" >/dev/null 2>&1; then
  cat <<'EOF'

Portless is running on fallback port 1355, so clean URLs like
https://nba-insight-ui.localhost will not work yet.

Stop the fallback proxy, then rerun this script:
  portless proxy stop -p 1355
  scripts/run_dev_portless.sh

If Portless asks for sudo on rerun, approve it so the proxy can bind to 443.
EOF
  exit 1
fi

api_pid=""
ui_pid=""

cleanup() {
  if [[ -n "$ui_pid" ]]; then
    kill "$ui_pid" 2>/dev/null || true
  fi
  if [[ -n "$api_pid" ]]; then
    kill "$api_pid" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

scripts/run_api_portless.sh &
api_pid=$!

NBA_INSIGHT_API_URL="${NBA_INSIGHT_API_URL:-https://nba-insight-api.localhost}" scripts/run_web_ui_portless.sh &
ui_pid=$!

echo
echo "NBA Insights dev URLs:"
echo "  UI:  https://nba-insight-ui.localhost"
echo "  API: https://nba-insight-api.localhost"
echo

while true; do
  if ! kill -0 "$api_pid" 2>/dev/null; then
    wait "$api_pid"
    exit $?
  fi

  if ! kill -0 "$ui_pid" 2>/dev/null; then
    wait "$ui_pid"
    exit $?
  fi

  sleep 1
done
