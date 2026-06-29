<template>
  <UiPanel title="接收状态" :subtitle="subtitle">
    <div class="status-grid">
      <div class="status-row">
        <span>{{ label }}</span>
        <strong :class="{ ok: running }">{{ stateText }}</strong>
        <small>{{ endpointText }}</small>
      </div>
      <div class="status-row">
        <span>最近计数</span>
        <strong>{{ received }}</strong>
        <small>后端本次进程已接收事件数</small>
      </div>
    </div>
  </UiPanel>
</template>

<script setup>
import { computed } from 'vue';
import UiPanel from '../ui/UiPanel.vue';

const props = defineProps({
  channel: {
    type: String,
    required: true,
  },
  receiver: {
    type: Object,
    default: null,
  },
});

const labelByChannel = {
  syslog: 'Syslog UDP',
  snmp_trap: 'SNMP Trap UDP',
  grpc_telemetry: 'Telemetry API',
};

const subtitleByChannel = {
  syslog: 'FRR lab 真实接口事件会通过 UDP Syslog 发到这里。',
  snmp_trap: 'FRR lab 真实接口事件会通过标准 SNMP Trap 发到这里。',
  grpc_telemetry: 'Telemetry 当前走 HTTP 接入端点，后续可替换为 gRPC/gNMI receiver。',
};

const label = computed(() => labelByChannel[props.channel] || props.channel);
const subtitle = computed(() => subtitleByChannel[props.channel] || '');
const running = computed(() => (props.channel === 'grpc_telemetry' ? true : Boolean(props.receiver?.running)));
const stateText = computed(() => (running.value ? '可接收' : '未监听'));
const received = computed(() => props.receiver?.received ?? 0);
const endpointText = computed(() => {
  if (props.channel === 'grpc_telemetry') {
    return 'POST /api/events/telemetry';
  }
  const host = props.receiver?.host || '0.0.0.0';
  const port = props.receiver?.port || '-';
  return `${host}:${port}`;
});
</script>

<style scoped>
.status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.status-row {
  display: grid;
  gap: 5px;
  min-width: 0;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.status-row span,
.status-row small {
  color: var(--nx-text-dim);
}

.status-row strong {
  min-width: 0;
  overflow: hidden;
  color: var(--nx-warning);
  font-size: 18px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-row strong.ok {
  color: var(--nx-success);
}

@media (max-width: 720px) {
  .status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
