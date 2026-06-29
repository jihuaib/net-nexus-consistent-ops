#!/bin/sh
set -eu

SNMP_COMMUNITY="${SNMP_COMMUNITY:-public}"
NETNEXUS_DEVICE="${NETNEXUS_DEVICE:-$(hostname)}"
resolve_ipv4_host() {
  resolved="$(getent ahostsv4 "$1" 2>/dev/null | awk 'NR == 1 {print $1}')"
  if [ -n "${resolved}" ]; then
    printf '%s' "${resolved}"
  else
    printf '%s' "$1"
  fi
}

NETNEXUS_EVENT_COLLECTOR_HOST="$(resolve_ipv4_host "${NETNEXUS_EVENT_COLLECTOR_HOST:-host.docker.internal}")"
NETNEXUS_SYSLOG_PORT="${NETNEXUS_SYSLOG_PORT:-1514}"
NETNEXUS_TRAP_PORT="${NETNEXUS_TRAP_PORT:-1162}"
NETNEXUS_LINK_EVENT_AGENT_ENABLED="${NETNEXUS_LINK_EVENT_AGENT_ENABLED:-1}"
export NETNEXUS_EVENT_COLLECTOR_HOST NETNEXUS_SYSLOG_PORT NETNEXUS_TRAP_PORT

mkdir -p /var/agentx /run/lldpd /var/run/lldpd /var/lib/net-snmp /var/log/frr
chmod 755 /var/agentx

cat > /etc/syslog.conf <<EOF
*.* @${NETNEXUS_EVENT_COLLECTOR_HOST}:${NETNEXUS_SYSLOG_PORT}
EOF

if command -v syslogd >/dev/null 2>&1; then
  syslogd -O /proc/1/fd/1 -R "${NETNEXUS_EVENT_COLLECTOR_HOST}:${NETNEXUS_SYSLOG_PORT}" -L || true
fi

cat > /etc/snmp/snmpd.conf <<EOF
agentAddress udp:0.0.0.0:161
rocommunity ${SNMP_COMMUNITY} 0.0.0.0/0
sysName ${NETNEXUS_DEVICE}
sysLocation NetNexus FRR SNMP lab
sysContact netnexus
view all included .1 80
master agentx
agentXSocket /var/agentx/master
agentXPerms 777 777
pass_persist .1.0.8802.1.1.2 /usr/local/bin/netnexus-lldp-mib-agent.py
EOF

snmpd -f -Lo -C -c /etc/snmp/snmpd.conf &

lldpd -I "eth*" || true

if [ "${NETNEXUS_LINK_EVENT_AGENT_ENABLED}" != "0" ]; then
  /usr/local/bin/netnexus-link-event-agent.py &
fi

exec /usr/lib/frr/docker-start
