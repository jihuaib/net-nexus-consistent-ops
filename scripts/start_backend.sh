#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

cd "$BACKEND_DIR"

if [ ! -x ".venv/bin/uvicorn" ]; then
  "$ROOT_DIR/scripts/setup_backend.sh"
fi

".venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8010}"
