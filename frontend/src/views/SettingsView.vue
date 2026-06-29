<template>
  <section class="view">
    <PageHeader
      eyebrow="Settings"
      title="系统设置"
      subtitle="集中管理大模型接入配置和当前运行状态。API Key 不回显，页面配置写入当前后端进程内存。"
    >
      <template #actions>
        <button class="secondary" :disabled="loading" @click="$emit('refresh')">刷新</button>
      </template>
    </PageHeader>

    <section class="settings-grid">
      <LlmConfigPanel :config="llmConfig || health?.llm" :loading="loading" @save="$emit('save-llm-config', $event)" />
      <SystemStatusPanel :health="health" :llm-config="llmConfig" :topology="topology" />
    </section>
  </section>
</template>

<script setup>
import LlmConfigPanel from '../components/LlmConfigPanel.vue';
import SystemStatusPanel from '../components/SystemStatusPanel.vue';
import PageHeader from '../components/ui/PageHeader.vue';

defineProps({
  loading: Boolean,
  health: Object,
  llmConfig: Object,
  topology: Object,
});

defineEmits(['save-llm-config', 'refresh']);
</script>

<style scoped>
.view {
  display: grid;
  align-content: start;
  gap: 8px;
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: 8px;
}

@media (max-width: 980px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
