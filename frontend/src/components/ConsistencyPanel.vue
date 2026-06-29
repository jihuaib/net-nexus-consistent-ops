<template>
  <UiPanel title="一致性验证">
    <template #actions>
      <button class="secondary" :disabled="loading" @click="$emit('test')">测试</button>
    </template>

    <div class="score-line">
      <span>总分</span>
      <strong>{{ consistency?.overall_consistency_score ?? '--' }}</strong>
    </div>
    <div v-if="consistency" class="mode-list">
      <div v-for="mode in consistency.mode_results" :key="mode.session_mode" class="mode">
        <span>{{ mode.session_mode }}</span>
        <strong>{{ mode.consistent_runs }}/{{ mode.total_runs }}</strong>
      </div>
    </div>
    <p v-else class="empty">运行后展示单会话和多会话一致性结果。</p>
  </UiPanel>
</template>

<script setup>
import UiPanel from './ui/UiPanel.vue';

defineProps({
  consistency: Object,
  loading: Boolean,
});

defineEmits(['test']);
</script>

<style scoped>
.score-line,
.mode {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.score-line {
  align-items: center;
  margin-bottom: 10px;
}

.score-line strong,
.mode strong {
  color: var(--nx-success);
}

.score-line strong {
  font-size: 28px;
}

.mode-list {
  display: grid;
  gap: 9px;
}

.mode span,
.empty {
  color: var(--nx-text-dim);
}
</style>
