<template>
  <aside class="app-sidebar">
    <header class="head">
      <div>
        <div class="head__title">{{ activeItem.label }}</div>
        <div class="head__count">{{ activeItem.description }}</div>
      </div>
    </header>

    <nav class="nav-list" aria-label="主导航">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="nav-row"
        :class="{ active: item.id === activeView }"
        @click="$emit('update:active-view', item.id)"
      >
        <component :is="item.icon" :size="17" :stroke-width="1.9" />
        <span>
          <strong>{{ item.label }}</strong>
          <small>{{ item.description }}</small>
        </span>
      </button>
    </nav>

    <section class="runtime-panel">
      <h2>运行状态</h2>
      <div class="runtime-row">
        <span>后端</span>
        <strong>{{ health?.status || 'unknown' }}</strong>
      </div>
      <div class="runtime-row">
        <span>LLM</span>
        <strong :class="{ ok: llmReady }">{{ llmReady ? '已配置' : '未配置' }}</strong>
      </div>
      <div class="runtime-row">
        <span>拓扑</span>
        <strong>{{ topologyText }}</strong>
      </div>
    </section>
  </aside>
</template>

<script setup>
import { computed } from 'vue';
import { Bot, Database, RadioReceiver, RadioTower, Satellite } from '@lucide/vue';

const props = defineProps({
  activeView: {
    type: String,
    default: 'diagnosis',
  },
  health: Object,
  llmConfig: Object,
  topology: Object,
});

defineEmits(['update:active-view']);

const navItems = [
  {
    id: 'diagnosis',
    label: '诊断',
    icon: Bot,
    description: 'Agent、拓扑与一致性',
  },
  {
    id: 'mib',
    label: 'MIB',
    icon: Database,
    description: '编译与 OID Tree',
  },
  {
    id: 'events-syslog',
    label: 'Syslog',
    icon: RadioTower,
    description: '日志事件上报',
  },
  {
    id: 'events-trap',
    label: 'SNMP',
    icon: RadioReceiver,
    description: 'Trap 告警上报',
  },
  {
    id: 'events-telemetry',
    label: 'gRPC',
    icon: Satellite,
    description: 'Telemetry 指标',
  },
];

const activeItem = computed(() => navItems.find((item) => item.id === props.activeView) || navItems[0]);
const llmReady = computed(() => props.llmConfig?.configured || props.health?.llm?.configured);
const topologyText = computed(() => {
  const discovery = props.topology?.discovery || {};
  const nodes = discovery.node_count ?? props.topology?.nodes?.length ?? 0;
  const edges = discovery.edge_count ?? props.topology?.edges?.length ?? 0;
  return `${nodes} 设备 / ${edges} 链路`;
});
</script>

<style scoped>
.app-sidebar {
  width: 240px;
  flex: 0 0 240px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--nx-border);
  background: var(--nx-surface);
}

.head {
  display: flex;
  align-items: center;
  min-height: 62px;
  padding: 12px 14px 9px;
}

.head__title {
  color: var(--nx-text);
  font-size: 14px;
  font-weight: 700;
}

.head__count {
  margin-top: 3px;
  color: var(--nx-text-dim);
  font-size: 11px;
}

.nav-list {
  display: grid;
  gap: 4px;
  padding: 8px;
  border-top: 1px solid var(--nx-border);
  border-bottom: 1px solid var(--nx-border);
}

.nav-row {
  width: 100%;
  min-height: 48px;
  justify-content: flex-start;
  gap: 9px;
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 7px 9px;
  color: var(--nx-text-dim);
  background: transparent;
  text-align: left;
}

.nav-row:hover {
  border-color: var(--nx-border);
  color: var(--nx-text);
  background: var(--nx-surface-2);
}

.nav-row.active {
  border-color: var(--nx-accent-border-soft);
  color: var(--nx-accent);
  background: var(--nx-accent-soft);
}

.nav-row span {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.nav-row strong,
.nav-row small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-row strong {
  color: inherit;
  font-size: 12px;
}

.nav-row small {
  font-size: 11px;
}

.runtime-panel {
  margin-top: auto;
  display: grid;
  gap: 7px;
  padding: 12px;
  border-top: 1px solid var(--nx-border);
}

.runtime-panel h2 {
  margin: 0 0 4px;
  font-size: 12px;
}

.runtime-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 30px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 0 8px;
  background: var(--nx-bg);
}

.runtime-row span {
  color: var(--nx-text-dim);
}

.runtime-row strong {
  min-width: 0;
  overflow: hidden;
  color: var(--nx-text);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-row strong.ok {
  color: var(--nx-success);
}

@media (max-width: 860px) {
  .app-sidebar {
    width: 176px;
    flex-basis: 176px;
  }
}

@media (max-width: 640px) {
  .app-sidebar {
    display: none;
  }
}
</style>
