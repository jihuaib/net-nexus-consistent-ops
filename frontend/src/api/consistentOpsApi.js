import { apiBase, request, webSocketUrl } from './http';

const faultCaseId = 'live-snmp-current';

export function fetchHealth() {
  return request('/api/health');
}

export function fetchLlmConfig() {
  return request('/api/llm/config');
}

export function fetchTopology() {
  return request('/api/topology');
}

export function fetchTopologyCapabilities() {
  return request('/api/topology/discovery-capabilities');
}

export function fetchTopologyDiscoveryConfig() {
  return request('/api/topology/discovery-config');
}

export function fetchEvents({ limit = 200, sinceSeconds = 3600, deviceId = '', channel = '' } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    since_seconds: String(sinceSeconds),
  });
  if (deviceId) {
    params.set('device_id', deviceId);
  }
  if (channel) {
    params.set('channel', channel);
  }
  return request(`/api/events?${params.toString()}`);
}

export function fetchEventCorrelation({ windowSeconds = 300, deviceId = '' } = {}) {
  const params = new URLSearchParams({
    window_seconds: String(windowSeconds),
  });
  if (deviceId) {
    params.set('device_id', deviceId);
  }
  return request(`/api/events/correlation?${params.toString()}`);
}

export function eventStreamUrl({ channel = '' } = {}) {
  const params = new URLSearchParams();
  if (channel) {
    params.set('channel', channel);
  }
  const query = params.toString();
  return webSocketUrl(`/api/events/ws${query ? `?${query}` : ''}`);
}

export function clearEvents() {
  return request('/api/events', {
    method: 'DELETE',
  });
}

export function ingestEvent(channel, payload) {
  const pathByChannel = {
    syslog: '/api/events/syslog',
    snmp_trap: '/api/events/trap',
    grpc_telemetry: '/api/events/telemetry',
  };
  return request(pathByChannel[channel] || '/api/events/syslog', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function saveTopologyDiscoveryConfig(config) {
  return request('/api/topology/discovery-config', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export function discoverTopology(payload = { mode: 'snmp_lldp' }) {
  return request('/api/topology/discover', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchMibProfiles() {
  return request('/api/mibs/profiles');
}

export function compileMibs(payload = { profile_id: 'snmp_lldp', include_tree: true }) {
  return request('/api/mibs/compile', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchMibTree({ profileId = 'snmp_lldp', parentOid = '', full = false } = {}) {
  const params = new URLSearchParams({
    profile_id: profileId,
    parent_oid: parentOid,
    full: String(full),
  });
  return request(`/api/mibs/tree?${params.toString()}`);
}

export function translateMibOid({ profileId = 'snmp_lldp', oid }) {
  return request('/api/mibs/translate', {
    method: 'POST',
    body: JSON.stringify({
      profile_id: profileId,
      oid,
    }),
  });
}

export function saveLlmConfig(config) {
  return request('/api/llm/config', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export async function fetchFacts() {
  const data = await request(`/api/facts?fault_case_id=${faultCaseId}`);
  return data.items;
}

export function chatWithAgent({ message, sessionId, topologyGroupId }) {
  return request('/api/agent/chat', {
    method: 'POST',
    body: JSON.stringify({
      message,
      fault_case_id: faultCaseId,
      session_id: sessionId,
      topology_group_id: topologyGroupId || null,
    }),
  });
}

export async function streamAgentChat({ message, sessionId, topologyGroupId, onEvent }) {
  const response = await fetch(`${apiBase}/api/agent/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      fault_case_id: faultCaseId,
      session_id: sessionId,
      topology_group_id: topologyGroupId || null,
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error('Streaming response body is not available');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      const text = line.trim();
      if (!text) {
        continue;
      }
      onEvent(JSON.parse(text));
    }
  }
  buffer += decoder.decode();
  const tail = buffer.trim();
  if (tail) {
    onEvent(JSON.parse(tail));
  }
}

export function fetchAgentSessions() {
  return request('/api/agent/sessions');
}

export function fetchAgentSession(sessionId) {
  return request(`/api/agent/sessions/${encodeURIComponent(sessionId)}`);
}

export function runConsistencyTest({ questions, runCount = 8 }) {
  return request('/api/consistency/test', {
    method: 'POST',
    body: JSON.stringify({
      fault_case_id: faultCaseId,
      session_modes: ['single_session', 'multi_session'],
      questions,
      run_count: runCount,
    }),
  });
}
