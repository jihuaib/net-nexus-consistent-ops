#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
  npm install
fi

VITE_API_BASE="${VITE_API_BASE:-http://127.0.0.1:8010}" ./node_modules/.bin/vite --host 127.0.0.1 --port "${PORT:-5178}"
