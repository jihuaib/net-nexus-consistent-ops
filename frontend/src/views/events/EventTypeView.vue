<template>
  <section class="view nms-event-view">
    <PageHeader :eyebrow="eyebrow" :title="title" :subtitle="subtitle">
      <template #actions>
        <span class="stream-state" :class="streamStateClass">{{ streamStateText }}</span>
        <button class="secondary" :disabled="loading" @click="loadEvents">
          <RefreshCw :size="15" />
          <span>刷新</span>
        </button>
        <button class="secondary danger" :disabled="loading" @click="clearAll">
          <Trash2 :size="15" />
          <span>清空</span>
        </button>
      </template>
    </PageHeader>

    <EventKpiStrip
      :channel="channel"
      :receiver="activeReceiver"
      :stream-state="streamState"
      :visible-count="filteredEvents.length"
      :events="filteredEvents"
      :correlation="correlation"
    />

    <EventFilterBar v-model="filters" :event-types="eventTypes" @reset="resetFilters" />

    <section class="event-workbench">
      <EventOperationsTable
        :title="listTitle"
        :events="filteredEvents"
        :selected-id="selectedEvent?.event_id || ''"
        :empty-text="emptyText"
        @select="selectEvent"
      />
      <EventDetailPanel :event="selectedEvent" />
    </section>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { RefreshCw, Trash2 } from '@lucide/vue';
import { clearEvents, eventStreamUrl, fetchEventCorrelation, fetchEvents } from '../../api/consistentOpsApi';
import EventDetailPanel from '../../components/events/EventDetailPanel.vue';
import EventFilterBar from '../../components/events/EventFilterBar.vue';
import EventKpiStrip from '../../components/events/EventKpiStrip.vue';
import EventOperationsTable from '../../components/events/EventOperationsTable.vue';
import PageHeader from '../../components/ui/PageHeader.vue';

const props = defineProps({
  channel: {
    type: String,
    required: true,
  },
  eyebrow: {
    type: String,
    default: 'Events',
  },
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    default: '',
  },
  listTitle: {
    type: String,
    default: '事件列表',
  },
});

const loading = ref(false);
const events = ref([]);
const receivers = ref({});
const correlation = ref(null);
const streamState = ref('connecting');
const selectedEventId = ref('');
const filters = ref({
  severity: '',
  eventType: '',
  device: '',
  keyword: '',
});
let socket = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let closing = false;

const emptyText = computed(() => {
  if (events.value.length) {
    return '当前过滤条件下没有匹配事件。';
  }
  return `还没有收到 ${props.title} 事件。`;
});
const activeReceiver = computed(() => {
  if (props.channel === 'syslog') {
    return receivers.value?.syslog;
  }
  if (props.channel === 'snmp_trap') {
    return receivers.value?.snmp_trap;
  }
  return null;
});
const streamStateClass = computed(() => ({
  connected: streamState.value === 'connected',
  connecting: streamState.value === 'connecting' || streamState.value === 'reconnecting',
  closed: streamState.value === 'closed',
}));
const streamStateText = computed(() => {
  if (streamState.value === 'connected') {
    return '实时已连接';
  }
  if (streamState.value === 'reconnecting') {
    return '重连中';
  }
  if (streamState.value === 'closed') {
    return '已断开';
  }
  return '连接中';
});
const eventTypes = computed(() => {
  const types = events.value.map((event) => event.event_type).filter(Boolean);
  return [...new Set(types)].sort((left, right) => left.localeCompare(right));
});
const filteredEvents = computed(() => {
  const severity = filters.value.severity.trim().toLowerCase();
  const eventType = filters.value.eventType.trim();
  const device = filters.value.device.trim().toLowerCase();
  const keyword = filters.value.keyword.trim().toLowerCase();

  return events.value.filter((event) => {
    if (severity && String(event.severity || '').toLowerCase() !== severity) {
      return false;
    }
    if (eventType && event.event_type !== eventType) {
      return false;
    }
    if (device && !String(event.device_id || '').toLowerCase().includes(device)) {
      return false;
    }
    if (!keyword) {
      return true;
    }
    const searchable = [
      event.event_type,
      event.device_id,
      event.object,
      event.source_ip,
      event.message,
      event.raw,
      JSON.stringify(event.attributes || {}),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return searchable.includes(keyword);
  });
});
const selectedEvent = computed(() => {
  if (!filteredEvents.value.length) {
    return null;
  }
  return filteredEvents.value.find((event) => event.event_id === selectedEventId.value) || filteredEvents.value[0];
});

watch(filteredEvents, ensureSelection);

onMounted(async () => {
  await loadEvents();
  connectStream();
});

onBeforeUnmount(() => {
  closeStream();
});

async function loadEvents() {
  if (loading.value) {
    return;
  }
  await fetchLatest({ showLoading: true });
}

async function fetchLatest({ showLoading = false } = {}) {
  if (showLoading) {
    loading.value = true;
  }
  try {
    const data = await fetchEvents({ limit: 300, sinceSeconds: 3600, channel: props.channel });
    const correlationData = await fetchEventCorrelation({ windowSeconds: 300 });
    events.value = data.items || [];
    receivers.value = data.receivers || {};
    correlation.value = correlationData;
    ensureSelection();
  } finally {
    if (showLoading) {
      loading.value = false;
    }
  }
}

async function clearAll() {
  loading.value = true;
  try {
    await clearEvents();
    events.value = [];
    selectedEventId.value = '';
    await fetchLatest();
  } finally {
    loading.value = false;
  }
}

function connectStream() {
  closing = false;
  clearReconnect();
  streamState.value = reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
  socket = new WebSocket(eventStreamUrl({ channel: props.channel }));

  socket.addEventListener('open', () => {
    streamState.value = 'connected';
    reconnectAttempts = 0;
  });

  socket.addEventListener('message', async (message) => {
    let payload = null;
    try {
      payload = JSON.parse(message.data);
    } catch {
      return;
    }
    if (payload.type === 'event' && payload.event) {
      appendEvent(payload.event);
      bumpReceiver(payload.event.channel);
      await refreshCorrelation();
    }
    if (payload.type === 'reset') {
      events.value = [];
      await refreshCorrelation();
    }
  });

  socket.addEventListener('close', () => {
    if (closing) {
      streamState.value = 'closed';
      return;
    }
    scheduleReconnect();
  });

  socket.addEventListener('error', () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.close();
    }
  });
}

function closeStream() {
  closing = true;
  clearReconnect();
  if (socket) {
    socket.close();
    socket = null;
  }
}

function scheduleReconnect() {
  reconnectAttempts += 1;
  streamState.value = 'reconnecting';
  const delay = Math.min(1000 * reconnectAttempts, 8000);
  reconnectTimer = window.setTimeout(connectStream, delay);
}

function clearReconnect() {
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function appendEvent(event) {
  if (event.channel !== props.channel) {
    return;
  }
  if (events.value.some((item) => item.event_id === event.event_id)) {
    return;
  }
  events.value = [event, ...events.value].slice(0, 300);
  selectedEventId.value = event.event_id;
}

function bumpReceiver(channel) {
  if (channel === 'syslog' && receivers.value?.syslog) {
    receivers.value = {
      ...receivers.value,
      syslog: { ...receivers.value.syslog, received: (receivers.value.syslog.received || 0) + 1 },
    };
  }
  if (channel === 'snmp_trap' && receivers.value?.snmp_trap) {
    receivers.value = {
      ...receivers.value,
      snmp_trap: { ...receivers.value.snmp_trap, received: (receivers.value.snmp_trap.received || 0) + 1 },
    };
  }
}

async function refreshCorrelation() {
  correlation.value = await fetchEventCorrelation({ windowSeconds: 300 });
}

function selectEvent(event) {
  selectedEventId.value = event?.event_id || '';
}

function resetFilters() {
  filters.value = {
    severity: '',
    eventType: '',
    device: '',
    keyword: '',
  };
}

function ensureSelection() {
  if (!filteredEvents.value.length) {
    selectedEventId.value = '';
    return;
  }
  if (!filteredEvents.value.some((event) => event.event_id === selectedEventId.value)) {
    selectedEventId.value = filteredEvents.value[0].event_id;
  }
}
</script>

<style scoped>
.view {
  display: grid;
  gap: 12px;
}

.event-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 360px);
  gap: 12px;
  align-items: start;
  min-width: 0;
}

.stream-state {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  border: 1px solid var(--nx-border);
  border-radius: 999px;
  padding: 0 9px;
  color: var(--nx-text-dim);
  background: var(--nx-surface-2);
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.stream-state.connected {
  border-color: var(--nx-success);
  color: var(--nx-success);
  background: var(--nx-success-soft);
}

.stream-state.connecting {
  border-color: var(--nx-warning);
  color: var(--nx-warning);
  background: var(--nx-warning-soft);
}

.stream-state.closed {
  border-color: var(--nx-danger-border);
  color: var(--nx-danger);
  background: var(--nx-danger-soft);
}

@media (max-width: 1120px) {
  .event-workbench {
    grid-template-columns: 1fr;
  }
}
</style>
