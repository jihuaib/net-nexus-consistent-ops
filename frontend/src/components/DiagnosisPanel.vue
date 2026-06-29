<template>
  <UiPanel title="结构化诊断">
    <div v-if="diagnosis" class="diagnosis">
      <span class="tag">{{ diagnosis.fault_type }}</span>
      <h3>{{ diagnosis.root_cause }}</h3>
      <dl>
        <div>
          <dt>故障指纹</dt>
          <dd>{{ diagnosis.fault_fingerprint }}</dd>
        </div>
        <div>
          <dt>置信度</dt>
          <dd>{{ diagnosis.confidence }}</dd>
        </div>
        <div>
          <dt>来源</dt>
          <dd>{{ diagnosis.diagnosis_source }}</dd>
        </div>
        <div>
          <dt>缓存</dt>
          <dd>{{ cacheLabel }}</dd>
        </div>
      </dl>
    </div>
    <p v-else class="empty">发送问题后展示诊断结果。</p>
  </UiPanel>
</template>

<script setup>
import { computed } from 'vue';
import UiPanel from './ui/UiPanel.vue';

const props = defineProps({
  diagnosis: Object,
});

const cacheLabel = computed(() => {
  if (!props.diagnosis) {
    return '-';
  }
  if (props.diagnosis.cache_hit) {
    return '命中';
  }
  return '首次写入';
});
</script>

<style scoped>
.diagnosis h3 {
  margin: 12px 0;
}

.tag {
  display: inline-block;
  width: fit-content;
  border: 1px solid var(--nx-accent-border);
  border-radius: 6px;
  padding: 3px 8px;
  color: var(--nx-accent);
  background: var(--nx-accent-soft);
  font-size: 11px;
  font-weight: 700;
}

dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

dl div {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 10px;
}

dt {
  color: var(--nx-text-dim);
}

dd {
  margin: 0;
  word-break: break-word;
}

.empty {
  color: var(--nx-text-dim);
}
</style>
