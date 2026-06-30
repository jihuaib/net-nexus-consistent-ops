<template>
  <section class="view">
    <PageHeader
      eyebrow="Diagnosis"
      title="诊断工作台"
      subtitle="会话式 Agent、结构化诊断、工具轨迹和一致性验证集中在这里，面向第二阶段单设备多异常一致性闭环。"
    >
      <template #actions>
        <button class="secondary" :disabled="loading" @click="$emit('refresh')">
          <RefreshCw :size="15" />
          <span>刷新</span>
        </button>
        <button :disabled="loading" @click="$emit('test-consistency')">
          <Gauge :size="15" />
          <span>一致性测试</span>
        </button>
      </template>
    </PageHeader>

    <section class="diagnosis-layout">
      <section class="conversation-pane" aria-label="Agent 会话">
        <AgentChat
          v-model:input="inputProxy"
          :loading="loading"
          :session-id="sessionId"
          :session-records="sessionRecords"
          :messages="messages"
          :quick-prompts="quickPrompts"
          @send="$emit('send')"
          @quick="$emit('quick', $event)"
          @switch-session="$emit('switch-session', $event)"
          @restore-session="$emit('restore-session', $event)"
          @reset-session="$emit('reset-session')"
        />
      </section>

      <aside class="analysis-pane" aria-label="诊断上下文">
        <TopologyPanel
          class="topology-card"
          :topology="topology"
          :selected-group-id="topologyGroupId"
          :capabilities="topologyCapabilities"
          :discovery-config="topologyDiscoveryConfig"
          :loading="loading"
          @discover="$emit('discover-topology', $event)"
          @select-group="$emit('select-topology-group', $event)"
          @configure="$emit('configure-topology')"
          @apply-frr-preset="$emit('apply-frr-topology-preset')"
          @apply-frr-bridge-preset="$emit('apply-frr-bridge-topology-preset')"
        />

        <section class="analysis-grid">
          <DiagnosisPanel class="analysis-card" :diagnosis="diagnosis" />
          <ToolTracePanel class="analysis-card" :tool-trace="toolTrace" />
          <ConsistencyPanel class="analysis-card" :consistency="consistency" :loading="loading" @test="$emit('test-consistency')" />
          <FactListPanel class="analysis-card" :facts="facts" />
        </section>
      </aside>
    </section>
  </section>
</template>

<script setup>
import { computed } from 'vue';
import { Gauge, RefreshCw } from '@lucide/vue';
import AgentChat from '../components/AgentChat.vue';
import ConsistencyPanel from '../components/ConsistencyPanel.vue';
import DiagnosisPanel from '../components/DiagnosisPanel.vue';
import FactListPanel from '../components/FactListPanel.vue';
import ToolTracePanel from '../components/ToolTracePanel.vue';
import TopologyPanel from '../components/TopologyPanel.vue';
import PageHeader from '../components/ui/PageHeader.vue';

const props = defineProps({
  loading: Boolean,
  sessionId: String,
  sessionRecords: {
    type: Array,
    default: () => [],
  },
  input: String,
  messages: {
    type: Array,
    default: () => [],
  },
  quickPrompts: {
    type: Array,
    default: () => [],
  },
  diagnosis: Object,
  toolTrace: {
    type: Array,
    default: () => [],
  },
  consistency: Object,
  facts: {
    type: Array,
    default: () => [],
  },
  topology: Object,
  topologyGroupId: {
    type: String,
    default: 'all',
  },
  topologyCapabilities: Object,
  topologyDiscoveryConfig: Object,
});

const emit = defineEmits([
  'update:input',
  'send',
  'quick',
  'switch-session',
  'restore-session',
  'reset-session',
  'test-consistency',
  'refresh',
  'discover-topology',
  'select-topology-group',
  'configure-topology',
  'apply-frr-topology-preset',
  'apply-frr-bridge-topology-preset',
]);

const inputProxy = computed({
  get: () => props.input,
  set: (value) => emit('update:input', value),
});
</script>

<style scoped>
.view {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 8px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.diagnosis-layout {
  display: grid;
  grid-template-columns: minmax(440px, 1.1fr) minmax(380px, 0.9fr);
  gap: 8px;
  min-height: 0;
  overflow: hidden;
}

.conversation-pane,
.analysis-pane,
.analysis-grid {
  min-height: 0;
  min-width: 0;
}

.conversation-pane {
  overflow: hidden;
}

.conversation-pane :deep(.workspace) {
  height: 100%;
  min-height: 0;
}

.conversation-pane :deep(.chat-window) {
  min-height: 0;
}

.analysis-pane {
  display: grid;
  grid-template-rows: minmax(300px, 0.95fr) minmax(260px, 1.05fr);
  gap: 8px;
  overflow: hidden;
}

.topology-card,
.analysis-card {
  min-height: 0;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  gap: 8px;
  overflow: hidden;
}

.analysis-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.analysis-card :deep(> :not(.ui-panel-head)) {
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

@media (max-width: 980px) {
  .view {
    height: auto;
    min-height: 100%;
    overflow: visible;
  }

  .diagnosis-layout,
  .analysis-pane,
  .analysis-grid {
    grid-template-columns: 1fr;
    grid-template-rows: none;
    overflow: visible;
  }

  .conversation-pane :deep(.workspace) {
    height: auto;
  }

  .conversation-pane :deep(.chat-window) {
    max-height: 56vh;
    min-height: 320px;
  }

  .analysis-card {
    height: auto;
  }

  .analysis-card :deep(> :not(.ui-panel-head)) {
    overflow: visible;
  }
}
</style>
