#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE="${API_BASE:-http://127.0.0.1:8010}"

missing=()
for name in LLM_API_KEY LLM_BASE_URL LLM_MODEL; do
  if [ -z "${!name:-}" ]; then
    missing+=("$name")
  fi
done

if [ "${#missing[@]}" -gt 0 ]; then
  runtime_configured="$(python3 - "$API_BASE" <<'PY'
import json
import sys
import urllib.error
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1].rstrip("/") + "/api/llm/config", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    print("1" if payload.get("configured") else "0")
except Exception:
    print("0")
PY
)"
  if [ "$runtime_configured" != "1" ]; then
    echo "Missing LLM configuration. Provide environment variables or configure it from the page." >&2
    echo "Environment example:" >&2
    echo "  export LLM_BASE_URL=https://your-provider.example/v1" >&2
    echo "  export LLM_MODEL=your-model-name" >&2
    echo "  export LLM_API_KEY=***" >&2
    echo "Page entry:" >&2
    echo "  http://127.0.0.1:5178/ -> 大模型配置" >&2
    exit 2
  fi
fi

"$ROOT_DIR/scripts/start_frr_lab.sh"

python3 - "$API_BASE" <<'PY'
import json
import time
import sys
import urllib.request

api_base = sys.argv[1].rstrip("/")


def request(path, payload=None, method=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(api_base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


health = request("/api/health")
assert health["status"] == "ok", health
assert health["data_source"] == "reported_events", health

request(
    "/api/topology/discovery-config",
    {
        "profile_id": "snmp_lldp",
        "community": "public",
        "targets": ["127.0.0.1:11611", "127.0.0.1:11612", "127.0.0.1:11613", "127.0.0.1:11614"],
        "scan_cidrs": [],
    },
)

topology = request("/api/topology/discover", {"mode": "snmp_lldp"})
assert topology["discovery"]["node_count"] == 4, topology
assert topology["discovery"]["edge_count"] >= 1, topology

request("/api/events", method="DELETE")

print("Waiting for real FRR lab syslog and SNMP Trap after interface down...")
PY

docker exec netnexus-leaf-01 ip link set eth1 up >/dev/null 2>&1 || true
sleep 2
docker exec netnexus-leaf-01 ip link set eth1 down

python3 - "$API_BASE" <<'PY'
import json
import sys
import time
import urllib.request

api_base = sys.argv[1].rstrip("/")


def request(path, payload=None, method=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(api_base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


events = None
for _ in range(30):
    events = request("/api/events?limit=100&since_seconds=120")
    by_channel = events["summary"]["by_channel"]
    if by_channel.get("syslog", 0) >= 1 and by_channel.get("snmp_trap", 0) >= 1:
        break
    time.sleep(1)
else:
    raise AssertionError(events)

facts = request("/api/facts?fault_case_id=live-snmp-current")
items = facts["items"]
assert items, facts
assert any(item["source"] == "syslog" for item in items), facts
assert any(item["source"] == "snmp_trap" for item in items), facts
assert all(item["fact_type"] not in {"RAW_REPORTED_EVENT", "UNKNOWN_EVENT"} for item in items), facts

agent_response = request(
    "/api/agent/chat",
    {
        "message": "leaf-01 为什么业务不通",
        "fault_case_id": "live-snmp-current",
        "session_id": "check-phase2-agent",
    },
)
diagnosis = agent_response["diagnosis"]
assert diagnosis["fault_type"], diagnosis
assert diagnosis["fault_fingerprint"].startswith("fp_"), diagnosis
assert len(agent_response["history"]) == 2, agent_response
assert len(agent_response["tool_trace"]) >= 5, agent_response

consistency = request(
    "/api/consistency/test",
    {
        "fault_case_id": "live-snmp-current",
        "session_modes": ["single_session", "multi_session"],
        "run_count": 8,
    },
)
assert consistency["passed"] is True, consistency
assert consistency["overall_consistency_score"] == 1.0, consistency

print("Phase 2 API check passed")
print("fault_fingerprint:", diagnosis["fault_fingerprint"])
print("overall_consistency_score:", consistency["overall_consistency_score"])
print("event_channels:", events["summary"]["by_channel"])
PY
