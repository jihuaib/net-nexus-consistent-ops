import { onBeforeUnmount, onMounted, ref } from 'vue';
import {
  discoverTopology as discoverTopologyApi,
  eventStreamUrl,
  fetchAgentSession,
  fetchAgentSessions,
  fetchFacts,
  fetchHealth,
  fetchLlmConfig,
  fetchTopology,
  fetchTopologyCapabilities,
  fetchTopologyDiscoveryConfig,
  runConsistencyTest,
  saveLlmConfig,
  saveTopologyDiscoveryConfig,
  streamAgentChat,
} from '../api/consistentOpsApi';
import { normalizeErrorAlert, useAlerts } from './useAlerts';

const welcomeMessage =
  '我是运维诊断 Agent。你可以从接口、业务不可达、BGP 等角度提问；同一故障下，我会基于故障指纹和诊断缓存保持一致结论。';

const newSessionMessage =
  '已创建新会话。你可以换一种问法重新诊断，系统仍会基于同一故障指纹保持根因一致。';

const SESSION_STORAGE_KEY = 'netnexus.consistentops.agent.sessions';
const ACTIVE_SESSION_STORAGE_KEY = 'netnexus.consistentops.agent.activeSessionId';
const ALL_TOPOLOGY_GROUPS = 'all';

export const quickPrompts = [
  '帮我分析当前故障',
  'leaf-01 为什么业务不通',
  '是不是 BGP 的问题',
  '相关路由为什么缺失',
  'FIB 表项为什么没有下发',
  '业务探测不可达的根因是什么',
  '重新诊断一下 leaf-01',
];

export function useAgentWorkspace() {
  const storedRecords = readStoredSessionRecords();
  const initialSessionId = readStoredActiveSessionId(storedRecords) || makeSessionId();
  const initialRecord = storedRecords.find((record) => record.sessionId === initialSessionId);
  const initialState = sessionStateFromRecord(initialSessionId, initialRecord);

  const loading = ref(false);
  const sessionId = ref(initialSessionId);
  const input = ref('leaf-01 为什么业务不通？');
  const health = ref(null);
  const llmConfig = ref(null);
  const topology = ref(null);
  const topologyGroupId = ref(initialRecord?.topologyGroupId || ALL_TOPOLOGY_GROUPS);
  const topologyCapabilities = ref(null);
  const topologyDiscoveryConfig = ref(null);
  const facts = ref(initialState.facts);
  const diagnosis = ref(initialState.diagnosis);
  const consistency = ref(null);
  const toolTrace = ref(initialState.toolTrace);
  const messages = ref(initialState.messages);
  const sessionRecords = ref(ensureSessionRecord(storedRecords, initialSessionId, initialState));
  const { pushAlert } = useAlerts();
  let topologyEventSocket = null;
  let topologyEventReconnectTimer = null;
  let topologyEventReconnectAttempts = 0;
  let topologyEventClosing = false;
  let topologyRefreshTimer = null;

  async function loadHealth() {
    health.value = await fetchHealth();
    llmConfig.value = await fetchLlmConfig();
  }

  async function loadFacts() {
    facts.value = await fetchFacts();
  }

  async function loadTopology() {
    topology.value = await fetchTopology();
    normalizeSelectedTopologyGroup();
  }

  async function loadTopologyCapabilities() {
    topologyCapabilities.value = await fetchTopologyCapabilities();
  }

  async function loadTopologyDiscoveryConfig() {
    topologyDiscoveryConfig.value = await fetchTopologyDiscoveryConfig();
  }

  async function refreshSessionRecords() {
    try {
      const data = await fetchAgentSessions();
      sessionRecords.value = mergeSessionRecords(sessionRecords.value, data.items || []);
      persistSessionRecords(sessionRecords.value);
    } catch {
      // Session listing is a convenience path. Local recovery remains available.
    }
  }

  async function discoverTopology(payload = { mode: 'snmp_lldp' }) {
    await withLoading(async () => {
      topology.value = await discoverTopologyApi(payload);
      normalizeSelectedTopologyGroup();
      const nodeCount = topology.value?.discovery?.node_count ?? topology.value?.nodes?.length ?? 0;
      const edgeCount = topology.value?.discovery?.edge_count ?? topology.value?.edges?.length ?? 0;
      pushAlert({
        type: 'success',
        title: '拓扑发现完成',
        message: `已发现 ${nodeCount} 台设备、${edgeCount} 条链路。`,
      });
    });
  }

  async function sendMessage() {
    const message = input.value.trim();
    if (!message) {
      return;
    }
    await withLoading(async () => {
      const userMessage = {
        id: `local-user-${Date.now()}`,
        role: 'user',
        content: message,
        created_at: new Date().toISOString(),
      };
      const assistantDraft = {
        id: `stream-agent-${Date.now()}`,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
        streaming: true,
      };
      input.value = '';
      messages.value = [...messages.value, userMessage, assistantDraft];
      toolTrace.value = [];
      await streamAgentChat({
        message,
        sessionId: sessionId.value,
        topologyGroupId: selectedTopologyGroupForRequest(),
        onEvent: (event) => handleAgentStreamEvent(event, assistantDraft.id),
      });
      await loadFacts();
      saveCurrentSession();
    });
  }

  function handleAgentStreamEvent(event, assistantDraftId) {
    if (event.type === 'stage' && event.tool) {
      toolTrace.value = upsertToolTrace(toolTrace.value, event.tool);
      return;
    }
    if (event.type === 'text_delta') {
      appendAssistantDraft(assistantDraftId, event.delta || '');
      return;
    }
    if (event.type === 'final') {
      messages.value = [assistantMessage('welcome', welcomeMessage), ...(event.history || [])];
      diagnosis.value = event.diagnosis;
      toolTrace.value = event.tool_trace || toolTrace.value;
      return;
    }
    if (event.type === 'error') {
      const message = event.message || 'Agent streaming failed';
      messages.value = messages.value.map((item) =>
        item.id === assistantDraftId ? { ...item, content: `调用失败：${message}`, streaming: false } : item
      );
      throw new Error(message);
    }
  }

  function appendAssistantDraft(messageId, delta) {
    if (!delta) {
      return;
    }
    messages.value = messages.value.map((message) =>
      message.id === messageId ? { ...message, content: `${message.content || ''}${delta}` } : message
    );
  }

  async function sendQuick(prompt) {
    input.value = prompt;
    await sendMessage();
  }

  async function runConsistency() {
    await withLoading(async () => {
      consistency.value = await runConsistencyTest({
        questions: quickPrompts,
        runCount: 8,
      });
      pushAlert({
        type: 'success',
        title: '一致性测试完成',
        message: `总分 ${consistency.value?.overall_consistency_score ?? '-'}，结果 ${consistency.value?.passed ? '通过' : '未通过'}。`,
      });
    });
  }

  async function saveConfig(config) {
    await withLoading(async () => {
      llmConfig.value = await saveLlmConfig(config);
      await loadHealth();
      pushAlert({
        type: 'success',
        title: '模型配置已保存',
        message: llmConfig.value?.configured ? '大模型接入参数已生效。' : '配置已保存，但 API Key 或模型参数仍未完整。',
      });
    });
  }

  async function saveTopologyConfig(config) {
    await withLoading(async () => {
      topologyDiscoveryConfig.value = await saveTopologyDiscoveryConfig(config);
      await loadTopologyCapabilities();
      pushAlert({
        type: 'success',
        title: '拓扑发现配置已保存',
        message: topologyDiscoverySummary(topologyDiscoveryConfig.value),
      });
    });
  }

  function resetSession() {
    saveCurrentSession();
    const nextSessionId = makeSessionId();
    const nextState = {
      messages: [assistantMessage('new-session', newSessionMessage)],
      diagnosis: null,
      toolTrace: [],
      facts: [],
    };
    applySessionState(nextSessionId, nextState);
    topologyGroupId.value = ALL_TOPOLOGY_GROUPS;
    input.value = 'leaf-01 为什么业务不通？';
    saveCurrentSession();
  }

  async function switchSession(nextSessionId) {
    if (!nextSessionId) {
      return;
    }
    if (nextSessionId === sessionId.value) {
      await restoreSession(nextSessionId);
      return;
    }
    saveCurrentSession();
    await restoreSession(nextSessionId);
  }

  async function restoreSession(targetSessionId = sessionId.value) {
    await withLoading(async () => {
      const localRecord = sessionRecords.value.find((record) => record.sessionId === targetSessionId);
      const backendSession = await fetchSessionSafely(targetSessionId);
      const nextState = sessionStateFromSources(targetSessionId, localRecord, backendSession);
      applySessionState(targetSessionId, nextState);
      saveCurrentSession();
      pushAlert({
        type: 'info',
        title: '会话已恢复',
        message: sessionTitle(sessionRecords.value.find((record) => record.sessionId === targetSessionId)),
      });
    });
  }

  async function loadAll() {
    await withLoading(async () => {
      await loadHealth();
      await loadTopologyCapabilities();
      await loadTopologyDiscoveryConfig();
      await loadTopology();
    });
  }

  async function withLoading(task) {
    loading.value = true;
    try {
      await task();
    } catch (err) {
      pushAlert(normalizeErrorAlert(err));
    } finally {
      loading.value = false;
    }
  }

  function applySessionState(nextSessionId, state) {
    sessionId.value = nextSessionId;
    topologyGroupId.value = normalizeTopologyGroupId(state.topologyGroupId || topologyGroupId.value);
    messages.value = state.messages;
    diagnosis.value = state.diagnosis;
    toolTrace.value = state.toolTrace;
    facts.value = state.facts;
  }

  function saveCurrentSession() {
    const record = buildSessionRecord({
      sessionId: sessionId.value,
      messages: messages.value,
      diagnosis: diagnosis.value,
      toolTrace: toolTrace.value,
      facts: facts.value,
      topologyGroupId: topologyGroupId.value,
    });
    sessionRecords.value = upsertSessionRecord(sessionRecords.value, record);
    persistSessionRecords(sessionRecords.value);
    persistActiveSessionId(sessionId.value);
  }

  function selectTopologyGroup(nextGroupId) {
    topologyGroupId.value = normalizeTopologyGroupId(nextGroupId);
    saveCurrentSession();
  }

  function selectedTopologyGroupForRequest() {
    return topologyGroupId.value === ALL_TOPOLOGY_GROUPS ? null : topologyGroupId.value;
  }

  function normalizeSelectedTopologyGroup() {
    topologyGroupId.value = normalizeTopologyGroupId(topologyGroupId.value);
  }

  function normalizeTopologyGroupId(value) {
    const nextGroupId = value || ALL_TOPOLOGY_GROUPS;
    if (nextGroupId === ALL_TOPOLOGY_GROUPS) {
      return ALL_TOPOLOGY_GROUPS;
    }
    const groups = topology.value?.groups || [];
    return groups.some((group) => group.id === nextGroupId) ? nextGroupId : ALL_TOPOLOGY_GROUPS;
  }

  function connectTopologyEventStream() {
    topologyEventClosing = false;
    clearTopologyEventReconnect();
    topologyEventSocket = new WebSocket(eventStreamUrl());

    topologyEventSocket.addEventListener('open', () => {
      topologyEventReconnectAttempts = 0;
    });

    topologyEventSocket.addEventListener('message', (message) => {
      let payload = null;
      try {
        payload = JSON.parse(message.data);
      } catch {
        return;
      }
      if (payload.type === 'reset') {
        scheduleTopologyRefresh();
        return;
      }
      const event = payload.event || {};
      if (payload.type === 'event' && ['INTERFACE_OPER_DOWN', 'INTERFACE_OPER_UP'].includes(event.event_type)) {
        scheduleTopologyRefresh();
      }
    });

    topologyEventSocket.addEventListener('close', () => {
      if (topologyEventClosing) {
        return;
      }
      scheduleTopologyEventReconnect();
    });

    topologyEventSocket.addEventListener('error', () => {
      if (topologyEventSocket && topologyEventSocket.readyState === WebSocket.OPEN) {
        topologyEventSocket.close();
      }
    });
  }

  function closeTopologyEventStream() {
    topologyEventClosing = true;
    clearTopologyEventReconnect();
    if (topologyEventSocket) {
      topologyEventSocket.close();
      topologyEventSocket = null;
    }
  }

  function scheduleTopologyEventReconnect() {
    topologyEventReconnectAttempts += 1;
    const delay = Math.min(1000 * topologyEventReconnectAttempts, 8000);
    topologyEventReconnectTimer = window.setTimeout(connectTopologyEventStream, delay);
  }

  function clearTopologyEventReconnect() {
    if (topologyEventReconnectTimer) {
      window.clearTimeout(topologyEventReconnectTimer);
      topologyEventReconnectTimer = null;
    }
  }

  function scheduleTopologyRefresh() {
    clearScheduledTopologyRefresh();
    topologyRefreshTimer = window.setTimeout(async () => {
      try {
        await loadTopology();
      } catch (err) {
        pushAlert(normalizeErrorAlert(err));
      }
    }, 120);
  }

  function clearScheduledTopologyRefresh() {
    if (topologyRefreshTimer) {
      window.clearTimeout(topologyRefreshTimer);
      topologyRefreshTimer = null;
    }
  }

  onMounted(async () => {
    await loadAll();
    await refreshSessionRecords();
    connectTopologyEventStream();
    saveCurrentSession();
  });

  onBeforeUnmount(() => {
    closeTopologyEventStream();
    clearScheduledTopologyRefresh();
  });

  return {
    loading,
    sessionId,
    sessionRecords,
    input,
    health,
    llmConfig,
    topology,
    topologyGroupId,
    topologyCapabilities,
    topologyDiscoveryConfig,
    facts,
    diagnosis,
    consistency,
    toolTrace,
    messages,
    quickPrompts,
    loadAll,
    discoverTopology,
    sendMessage,
    sendQuick,
    runConsistency,
    saveConfig,
    saveTopologyConfig,
    resetSession,
    switchSession,
    restoreSession,
    selectTopologyGroup,
  };
}

async function fetchSessionSafely(sessionId) {
  try {
    return await fetchAgentSession(sessionId);
  } catch {
    return null;
  }
}

function makeSessionId() {
  return `agent-session-${Date.now()}`;
}

function assistantMessage(id, content) {
  return {
    id,
    role: 'assistant',
    content,
  };
}

function sessionStateFromRecord(sessionId, record) {
  return sessionStateFromSources(sessionId, record, null);
}

function sessionStateFromSources(sessionId, localRecord, backendSession) {
  const localHistory = sessionHistory(localRecord?.messages || []);
  const backendHistory = backendSession?.history || [];
  const history = mergeMessages(localHistory, backendHistory);
  const latestDiagnosis = latestMessageValue(history, 'diagnosis') || localRecord?.diagnosis || null;
  const latestToolTrace = latestMessageValue(history, 'tool_trace') || localRecord?.toolTrace || [];
  const latestTopologyGroupId =
    latestMessageValue(history, 'topology_group_id') || latestDiagnosis?.topology_group_id || localRecord?.topologyGroupId || ALL_TOPOLOGY_GROUPS;

  if (history.length) {
    return {
      messages: [assistantMessage('welcome', welcomeMessage), ...history],
      diagnosis: latestDiagnosis,
      toolTrace: latestToolTrace,
      facts: latestDiagnosis?.facts || localRecord?.facts || [],
      topologyGroupId: latestTopologyGroupId,
    };
  }

  if (localRecord?.messages?.length) {
    return {
      messages: localRecord.messages,
      diagnosis: localRecord.diagnosis || null,
      toolTrace: localRecord.toolTrace || [],
      facts: localRecord.facts || [],
      topologyGroupId: localRecord.topologyGroupId || ALL_TOPOLOGY_GROUPS,
    };
  }

  return {
    messages: [assistantMessage('welcome', welcomeMessage)],
    diagnosis: null,
    toolTrace: [],
    facts: [],
    topologyGroupId: ALL_TOPOLOGY_GROUPS,
  };
}

function buildSessionRecord({ sessionId, messages, diagnosis, toolTrace, facts, topologyGroupId }) {
  const history = sessionHistory(messages);
  const latestMessage = history[history.length - 1];
  return {
    sessionId,
    title: sessionTitleFromMessages(messages),
    updatedAt: latestMessage?.created_at || new Date().toISOString(),
    messageCount: history.length,
    messages,
    diagnosis,
    toolTrace,
    facts,
    topologyGroupId: topologyGroupId || ALL_TOPOLOGY_GROUPS,
  };
}

function sessionTitle(record) {
  return record?.title || '未命名会话';
}

function sessionTitleFromMessages(messages) {
  const firstUserMessage = sessionHistory(messages).find((message) => message.role === 'user');
  return compactTitle(firstUserMessage?.content || '新会话');
}

function compactTitle(content, limit = 24) {
  const normalized = String(content || '').replace(/\s+/g, ' ').trim();
  if (!normalized) {
    return '未命名会话';
  }
  return normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized;
}

function sessionHistory(messages) {
  return (messages || []).filter((message) => !['welcome', 'new-session'].includes(message.id));
}

function mergeMessages(existingMessages, incomingMessages) {
  const merged = [];
  const seen = new Set();
  for (const message of [...(existingMessages || []), ...(incomingMessages || [])]) {
    const key = messageKey(message);
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(message);
    }
  }
  return merged;
}

function upsertToolTrace(items, nextTool) {
  const current = Array.isArray(items) ? items : [];
  const index = current.findIndex((item) => item.name === nextTool.name);
  if (index === -1) {
    return [...current, nextTool];
  }
  return current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...nextTool } : item));
}

function messageKey(message) {
  return message?.id || `${message?.role || 'unknown'}:${message?.created_at || ''}:${message?.content || ''}`;
}

function latestMessageValue(messages, key) {
  for (const message of [...(messages || [])].reverse()) {
    if (message?.[key] != null) {
      return message[key];
    }
  }
  return null;
}

function ensureSessionRecord(records, sessionId, state) {
  return upsertSessionRecord(
    normalizeSessionRecords(records),
    buildSessionRecord({
      sessionId,
      messages: state.messages,
      diagnosis: state.diagnosis,
      toolTrace: state.toolTrace,
      facts: state.facts,
      topologyGroupId: state.topologyGroupId,
    })
  );
}

function upsertSessionRecord(records, nextRecord) {
  const nextRecords = [nextRecord, ...records.filter((record) => record.sessionId !== nextRecord.sessionId)];
  return normalizeSessionRecords(nextRecords).slice(0, 20);
}

function mergeSessionRecords(localRecords, backendRecords) {
  const normalizedLocalRecords = normalizeSessionRecords(localRecords);
  const byId = new Map(normalizedLocalRecords.map((record) => [record.sessionId, record]));
  for (const summary of backendRecords || []) {
    const sessionId = summary.session_id || summary.sessionId;
    if (!sessionId) {
      continue;
    }
    const current = byId.get(sessionId);
    byId.set(sessionId, {
      sessionId,
      title: current?.title && current.title !== '新会话' ? current.title : summary.title || sessionId,
      updatedAt: latestDateString(current?.updatedAt, summary.updated_at || summary.updatedAt),
      messageCount: Math.max(current?.messageCount || 0, summary.message_count || summary.messageCount || 0),
      messages: current?.messages || [],
      diagnosis: current?.diagnosis || null,
      toolTrace: current?.toolTrace || [],
      facts: current?.facts || [],
      topologyGroupId: current?.topologyGroupId || ALL_TOPOLOGY_GROUPS,
    });
  }
  return normalizeSessionRecords([...byId.values()]);
}

function normalizeSessionRecords(records) {
  return (Array.isArray(records) ? records : [])
    .filter((record) => record?.sessionId || record?.session_id)
    .map((record) => ({
      sessionId: record.sessionId || record.session_id,
      title: compactTitle(record.title || record.sessionId || record.session_id),
      updatedAt: record.updatedAt || record.updated_at || null,
      messageCount: Number(record.messageCount ?? record.message_count ?? 0),
      messages: Array.isArray(record.messages) ? record.messages : [],
      diagnosis: record.diagnosis || null,
      toolTrace: Array.isArray(record.toolTrace) ? record.toolTrace : [],
      facts: Array.isArray(record.facts) ? record.facts : [],
      topologyGroupId: record.topologyGroupId || record.topology_group_id || ALL_TOPOLOGY_GROUPS,
    }))
    .sort((left, right) => String(right.updatedAt || '').localeCompare(String(left.updatedAt || '')));
}

function latestDateString(left, right) {
  if (!left) {
    return right || null;
  }
  if (!right) {
    return left;
  }
  return String(left) > String(right) ? left : right;
}

function topologyDiscoverySummary(config) {
  const cidrCount = config?.scan_cidrs?.length || 0;
  const targetCount = config?.targets?.length || 0;
  if (cidrCount && targetCount) {
    return `已配置 ${cidrCount} 个管理网段和 ${targetCount} 个 seed IP。`;
  }
  if (cidrCount) {
    return `已配置 ${cidrCount} 个管理网段。`;
  }
  if (targetCount) {
    return `已配置 ${targetCount} 个 seed IP。`;
  }
  return '未配置目标，SNMP LLDP 发现前请填写管理网段或 seed IP。';
}

function readStoredSessionRecords() {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    return normalizeSessionRecords(JSON.parse(window.localStorage.getItem(SESSION_STORAGE_KEY) || '[]'));
  } catch {
    return [];
  }
}

function readStoredActiveSessionId(records) {
  if (typeof window === 'undefined') {
    return '';
  }
  const activeSessionId = window.localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY) || '';
  if (activeSessionId && records.some((record) => record.sessionId === activeSessionId)) {
    return activeSessionId;
  }
  return records[0]?.sessionId || '';
}

function persistSessionRecords(records) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(normalizeSessionRecords(records)));
}

function persistActiveSessionId(activeSessionId) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, activeSessionId);
}
