#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
  npm install
fi

FRONTEND_HOST="${FRONTEND_HOST:-${HOST:-0.0.0.0}}"
FRONTEND_PORT="${FRONTEND_PORT:-${PORT:-5178}}"
VITE_PROXY_TARGET="${VITE_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT:-8010}}"

echo "Starting development frontend on ${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "Proxying /api to ${VITE_PROXY_TARGET}"
if [ -n "${VITE_API_BASE:-}" ]; then
  VITE_API_BASE="$VITE_API_BASE" VITE_PROXY_TARGET="$VITE_PROXY_TARGET" ./node_modules/.bin/vite --mode development --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
else
  VITE_PROXY_TARGET="$VITE_PROXY_TARGET" ./node_modules/.bin/vite --mode development --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
fi
