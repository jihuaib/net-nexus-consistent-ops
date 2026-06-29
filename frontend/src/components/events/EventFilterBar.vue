<template>
  <section class="filter-bar" aria-label="事件过滤">
    <label>
      <span>级别</span>
      <select :value="modelValue.severity" @change="update('severity', $event.target.value)">
        <option value="">全部</option>
        <option value="critical">Critical</option>
        <option value="major">Major</option>
        <option value="warning">Warning</option>
        <option value="info">Info</option>
      </select>
    </label>
    <label>
      <span>类型</span>
      <select :value="modelValue.eventType" @change="update('eventType', $event.target.value)">
        <option value="">全部</option>
        <option v-for="type in eventTypes" :key="type" :value="type">{{ type }}</option>
      </select>
    </label>
    <label>
      <span>设备</span>
      <input :value="modelValue.device" placeholder="leaf-01" @input="update('device', $event.target.value)" />
    </label>
    <label class="search-field">
      <span>关键字</span>
      <input :value="modelValue.keyword" placeholder="对象、原文、来源地址" @input="update('keyword', $event.target.value)" />
    </label>
    <button class="secondary" type="button" @click="$emit('reset')">
      <RotateCcw :size="14" />
      <span>重置</span>
    </button>
  </section>
</template>

<script setup>
import { RotateCcw } from '@lucide/vue';

const props = defineProps({
  modelValue: {
    type: Object,
    required: true,
  },
  eventTypes: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['update:modelValue', 'reset']);

function update(key, value) {
  emit('update:modelValue', {
    ...props.modelValue,
    [key]: value,
  });
}
</script>

<style scoped>
.filter-bar {
  display: grid;
  grid-template-columns: 140px 180px 160px minmax(220px, 1fr) auto;
  gap: 10px;
  align-items: end;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  padding: 10px;
  background: var(--nx-surface-raised);
}

.filter-bar label {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.filter-bar label span {
  color: var(--nx-text-dim);
  font-size: 11px;
}

.filter-bar button {
  min-width: 78px;
}

@media (max-width: 980px) {
  .filter-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .filter-bar {
    grid-template-columns: 1fr;
  }
}
</style>
