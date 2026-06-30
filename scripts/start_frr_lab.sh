#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAB_DIR="$ROOT_DIR/labs/frr-spine-leaf"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "Docker Compose is required. Install Docker Desktop or docker compose plugin first." >&2
  exit 2
fi

FRR_BASE_IMAGE="${FRR_BASE_IMAGE:-ubuntu:24.04}"
DOCKER_BUILD_NETWORK="${DOCKER_BUILD_NETWORK:-}"
NETNEXUS_EVENT_COLLECTOR_HOST="${NETNEXUS_EVENT_COLLECTOR_HOST:-}"

if [ -z "$DOCKER_BUILD_NETWORK" ] && [ "$(uname -s)" = "Linux" ]; then
  DOCKER_BUILD_NETWORK="host"
fi

if [ -z "$NETNEXUS_EVENT_COLLECTOR_HOST" ] && [ "$(uname -s)" = "Linux" ]; then
  NETNEXUS_EVENT_COLLECTOR_HOST="172.30.0.1"
fi
export NETNEXUS_EVENT_COLLECTOR_HOST

BUILD_NETWORK_ARGS=()
if [ -n "$DOCKER_BUILD_NETWORK" ]; then
  BUILD_NETWORK_ARGS=(--network "$DOCKER_BUILD_NETWORK")
fi

echo "Building FRR lab image."
echo "Base image: $FRR_BASE_IMAGE"
if [ -n "$DOCKER_BUILD_NETWORK" ]; then
  echo "Docker build network: $DOCKER_BUILD_NETWORK"
fi
if [ -n "$NETNEXUS_EVENT_COLLECTOR_HOST" ]; then
  echo "Event collector host: $NETNEXUS_EVENT_COLLECTOR_HOST"
fi

docker build \
  "${BUILD_NETWORK_ARGS[@]}" \
  --build-arg "FRR_BASE_IMAGE=$FRR_BASE_IMAGE" \
  -t netnexus-frr-snmp:latest \
  -f "$LAB_DIR/Dockerfile.snmp" \
  "$LAB_DIR"

"${COMPOSE[@]}" -f "$LAB_DIR/docker-compose.yml" up -d

echo "FRR spine-leaf lab started."
if [ -n "$NETNEXUS_EVENT_COLLECTOR_HOST" ]; then
  echo "Syslog/Trap target: $NETNEXUS_EVENT_COLLECTOR_HOST:1514 / $NETNEXUS_EVENT_COLLECTOR_HOST:1162"
fi
echo "Validate BGP:"
echo "  docker exec netnexus-spine-01 vtysh -c 'show bgp summary'"
echo "Discover topology through SNMP/LLDP-MIB:"
echo "  curl -X POST http://127.0.0.1:8010/api/topology/discovery-config -H 'Content-Type: application/json' -d '{\"targets\":[\"127.0.0.1:11611\",\"127.0.0.1:11612\",\"127.0.0.1:11613\",\"127.0.0.1:11614\"],\"scan_cidrs\":[],\"community\":\"public\"}'"
echo "  curl -X POST http://127.0.0.1:8010/api/topology/discover -H 'Content-Type: application/json' -d '{\"mode\":\"snmp_lldp\"}'"
