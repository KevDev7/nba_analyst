#!/usr/bin/env bash
set -euo pipefail

if ! command -v portless >/dev/null 2>&1; then
  echo "Portless is not installed."
  echo "Install it with: npm install -g portless"
  echo "Fallback command:"
  echo "npm --prefix apps/web-ui run dev"
  exit 1
fi

portless nba-insight-ui sh -c 'npm --prefix apps/web-ui run dev -- --host 127.0.0.1 --port "$PORT"'
