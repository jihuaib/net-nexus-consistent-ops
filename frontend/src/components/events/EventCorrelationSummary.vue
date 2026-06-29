<template>
  <UiPanel title="关联窗口">
    <div class="summary-grid">
      <div>
        <span>事件</span>
        <strong>{{ correlation?.event_count ?? 0 }}</strong>
      </div>
      <div>
        <span>窗口</span>
        <strong>{{ correlation?.window_seconds ?? 300 }}s</strong>
      </div>
      <div>
        <span>设备</span>
        <strong>{{ deviceCount }}</strong>
      </div>
    </div>
  </UiPanel>
</template>

<script setup>
import { computed } from 'vue';
import UiPanel from '../ui/UiPanel.vue';

const props = defineProps({
  correlation: {
    type: Object,
    default: null,
  },
});

const deviceCount = computed(() => Object.keys(props.correlation?.summary?.by_device || {}).length);
</script>

<style scoped>
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.summary-grid div {
  display: grid;
  gap: 5px;
  min-width: 0;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.summary-grid span {
  color: var(--nx-text-dim);
}

.summary-grid strong {
  min-width: 0;
  overflow: hidden;
  font-size: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
