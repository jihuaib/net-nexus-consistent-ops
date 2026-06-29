<template>
  <section class="kpi-strip" aria-label="事件通道状态">
    <div class="kpi-item">
      <span>接收状态</span>
      <strong :class="{ ok: receiverRunning }">{{ receiverText }}</strong>
      <small>{{ endpointText }}</small>
    </div>
    <div class="kpi-item">
      <span>实时通道</span>
      <strong :class="streamClass">{{ streamText }}</strong>
      <small>WebSocket 推送</small>
    </div>
    <div class="kpi-item">
      <span>当前列表</span>
      <strong>{{ visibleCount }}</strong>
      <small>近 {{ windowSeconds }} 秒窗口 {{ correlationCount }} 条</small>
    </div>
    <div class="kpi-item">
      <span>严重级别</span>
      <strong>{{ alarmCount }}</strong>
      <small>critical / major / warning</small>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  channel: {
    type: String,
    required: true,
  },
  receiver: {
    type: Object,
    default: null,
  },
  streamState: {
    type: String,
    default: 'connecting',
  },
  visibleCount: {
    type: Number,
    default: 0,
  },
  events: {
    type: Array,
    default: () => [],
  },
  correlation: {
    type: Object,
    default: null,
  },
});

const receiverRunning = computed(() => (props.channel === 'grpc_telemetry' ? true : Boolean(props.receiver?.running)));
const receiverText = computed(() => (receiverRunning.value ? '接收中' : '未监听'));
const streamText = computed(() => {
  if (props.streamState === 'connected') return '已连接';
  if (props.streamState === 'reconnecting') return '重连中';
  if (props.streamState === 'closed') return '已断开';
  return '连接中';
});
const streamClass = computed(() => ({
  ok: props.streamState === 'connected',
  warn: props.streamState === 'connecting' || props.streamState === 'reconnecting',
  danger: props.streamState === 'closed',
}));
const endpointText = computed(() => {
  if (props.channel === 'grpc_telemetry') {
    return 'POST /api/events/telemetry';
  }
  const host = props.receiver?.host || '0.0.0.0';
  const port = props.receiver?.port || '-';
  return `${host}:${port}`;
});
const windowSeconds = computed(() => props.correlation?.window_seconds ?? 300);
const correlationCount = computed(() => props.correlation?.event_count ?? 0);
const alarmCount = computed(
  () => props.events.filter((event) => ['critical', 'major', 'warning'].includes(String(event.severity || '').toLowerCase())).length,
);
</script>

<style scoped>
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.kpi-item {
  display: grid;
  gap: 5px;
  min-width: 0;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  padding: 10px 11px;
  background: var(--nx-surface-raised);
}

.kpi-item span,
.kpi-item small {
  min-width: 0;
  overflow: hidden;
  color: var(--nx-text-dim);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kpi-item strong {
  min-width: 0;
  overflow: hidden;
  color: var(--nx-warning);
  font-size: 18px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kpi-item strong.ok {
  color: var(--nx-success);
}

.kpi-item strong.warn {
  color: var(--nx-warning);
}

.kpi-item strong.danger {
  color: var(--nx-danger);
}

@media (max-width: 1100px) {
  .kpi-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .kpi-strip {
    grid-template-columns: 1fr;
  }
}
</style>
