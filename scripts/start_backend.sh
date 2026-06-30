#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

cd "$BACKEND_DIR"

if [ ! -x ".venv/bin/uvicorn" ]; then
  "$ROOT_DIR/scripts/setup_backend.sh"
fi

BACKEND_HOST="${BACKEND_HOST:-${HOST:-0.0.0.0}}"
BACKEND_PORT="${BACKEND_PORT:-${PORT:-8010}}"

echo "Starting development backend on ${BACKEND_HOST}:${BACKEND_PORT}"
APP_ENV="${APP_ENV:-development}" ".venv/bin/python" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
