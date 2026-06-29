<template>
  <UiPanel title="本次分析输入事实">
    <div v-if="facts.length" class="fact-list">
      <article v-for="fact in facts" :key="fact.fact_id" class="fact">
        <strong>{{ fact.fact_type }}</strong>
        <span>{{ fact.device_id }} / {{ fact.object }}</span>
        <small>{{ fact.source }} · {{ fact.severity }}</small>
      </article>
    </div>
    <p v-else class="empty">发送问题并完成分析后展示本次使用的采集事实。</p>
  </UiPanel>
</template>

<script setup>
import UiPanel from './ui/UiPanel.vue';

defineProps({
  facts: {
    type: Array,
    default: () => [],
  },
});
</script>

<style scoped>
.fact-list {
  display: grid;
  gap: 9px;
}

.fact {
  display: grid;
  gap: 4px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.fact span,
.fact small,
.empty {
  color: var(--nx-text-dim);
}
</style>
