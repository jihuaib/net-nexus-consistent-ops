#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

cd "$BACKEND_DIR"

if [ ! -x ".venv/bin/python" ]; then
  "$ROOT_DIR/scripts/setup_backend.sh"
fi

APP_ENV="${APP_ENV:-production}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8010}"
BACKEND_WORKERS="${BACKEND_WORKERS:-2}"

echo "Starting production backend on ${BACKEND_HOST}:${BACKEND_PORT} with ${BACKEND_WORKERS} workers"
APP_ENV="$APP_ENV" ".venv/bin/python" -m uvicorn app.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  --workers "$BACKEND_WORKERS" \
  --proxy-headers

