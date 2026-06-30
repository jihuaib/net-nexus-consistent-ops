<template>
  <UiPanel title="本次分析输入事实">
    <div v-if="facts.length" class="fact-list">
      <article v-for="fact in facts" :key="fact.fact_id" class="fact">
        <strong>{{ fact.fact_type }}</strong>
        <span>{{ fact.device_id }} / {{ fact.object }}</span>
        <small>{{ fact.source }} · {{ fact.severity }}</small>
        <small v-if="contextLine(fact)" class="context-line">{{ contextLine(fact) }}</small>
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

function contextLine(fact) {
  const context = fact?.context || {};
  const parts = [];
  if (context.depends_on_interface) {
    parts.push(`依赖 ${context.depends_on_interface}`);
  }
  if (context.next_hop) {
    parts.push(`下一跳 ${context.next_hop}`);
  }
  if (context.remote_device) {
    parts.push(`远端 ${context.remote_device}`);
  }
  if (context.source_event_id) {
    parts.push(`事件 ${context.source_event_id}`);
  }
  return parts.join(' · ');
}
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

.context-line {
  overflow-wrap: anywhere;
}
</style>
