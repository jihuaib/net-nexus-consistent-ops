<template>
  <UiPanel title="系统状态">
    <div class="status-grid">
      <div>
        <span>后端</span>
        <strong>{{ health?.status || 'unknown' }}</strong>
      </div>
      <div>
        <span>阶段</span>
        <strong>{{ health?.phase || '--' }}</strong>
      </div>
      <div>
        <span>LLM</span>
        <strong>{{ llmStatus }}</strong>
      </div>
      <div>
        <span>拓扑</span>
        <strong>{{ topologySummary }}</strong>
      </div>
    </div>
  </UiPanel>
</template>

<script setup>
import { computed } from 'vue';
import UiPanel from './ui/UiPanel.vue';

const props = defineProps({
  health: Object,
  llmConfig: Object,
  topology: Object,
});

const llmStatus = computed(() => (props.llmConfig?.configured || props.health?.llm?.configured ? '已配置' : '未配置'));
const topologySummary = computed(() => {
  const discovery = props.topology?.discovery || {};
  const nodes = discovery.node_count ?? props.topology?.nodes?.length ?? 0;
  const edges = discovery.edge_count ?? props.topology?.edges?.length ?? 0;
  return `${nodes} / ${edges}`;
});
</script>

<style scoped>
.status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.status-grid div {
  display: grid;
  gap: 4px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.status-grid span {
  color: var(--nx-text-dim);
}

.status-grid strong {
  color: var(--nx-text);
}

@media (max-width: 640px) {
  .status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
