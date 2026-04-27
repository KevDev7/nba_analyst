#!/usr/bin/env bash
set -euo pipefail

if ! command -v portless >/dev/null 2>&1; then
  echo "Portless is not installed."
  echo "Install it with: npm install -g portless"
  echo "Fallback command:"
  echo "uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000"
  exit 1
fi

portless nba-analyst sh -c 'uvicorn apps.web.server:app --reload --host 127.0.0.1 --port "$PORT"'
