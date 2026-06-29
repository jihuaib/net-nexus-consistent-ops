#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$BACKEND_DIR"

if [ ! -x ".venv/bin/python" ]; then
  "$ROOT_DIR/scripts/setup_backend.sh"
fi

"$ROOT_DIR/scripts/start_frr_lab.sh"

ready=0
for _ in $(seq 1 30); do
  if ".venv/bin/python" - <<'PY' >/dev/null 2>&1; then
from app.infrastructure.topology.snmp_client import PysnmpWalkClient

targets = ["127.0.0.1:11611", "127.0.0.1:11612", "127.0.0.1:11613", "127.0.0.1:11614"]
client = PysnmpWalkClient()
for target in targets:
    output = client.walk(target, "public", ".1.3.6.1.2.1.1.5.0", 1.5)
    if " = " not in output:
        raise SystemExit(1)
PY
    ready=1
    break
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "FRR SNMP lab did not become ready in time." >&2
  exit 1
fi

docker exec netnexus-leaf-01 ip link set eth1 down
sleep 1

".venv/bin/python" -m unittest discover tests

cd "$FRONTEND_DIR"
npm run build

echo "Phase 2 backend tests and frontend build passed."
