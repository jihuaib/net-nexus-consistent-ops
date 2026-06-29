<template>
  <UiPanel title="工具调用轨迹">
    <div v-if="toolTrace.length" class="tool-list">
      <div v-for="tool in toolTrace" :key="tool.name" class="tool">
        <strong>{{ tool.name }}</strong>
        <span :class="['status', tool.status]">{{ tool.status }}</span>
        <p>{{ tool.summary }}</p>
      </div>
    </div>
    <p v-else class="empty">Agent 调用诊断工具后展示执行轨迹。</p>
  </UiPanel>
</template>

<script setup>
import UiPanel from './ui/UiPanel.vue';

defineProps({
  toolTrace: {
    type: Array,
    default: () => [],
  },
});
</script>

<style scoped>
.tool-list {
  display: grid;
  gap: 9px;
}

.tool {
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.tool p {
  margin: 6px 0 0;
  color: var(--nx-text-dim);
}

.status {
  display: inline-block;
  margin-left: 8px;
  border-radius: 6px;
  padding: 2px 7px;
  color: var(--nx-success);
  background: var(--nx-success-soft);
  font-size: 11px;
}

.status.success {
  color: var(--nx-success);
  background: var(--nx-success-soft);
}

.status.miss {
  color: var(--nx-warning);
  background: var(--nx-warning-soft);
}

.status.hit {
  color: var(--nx-accent);
  background: var(--nx-accent-soft);
}

.status.running {
  color: var(--nx-accent);
  background: var(--nx-accent-soft);
}

.status.skipped {
  color: var(--nx-text-dim);
  background: var(--nx-surface);
}

.empty {
  color: var(--nx-text-dim);
}
</style>
