<template>
  <UiPanel title="大模型配置">
    <div class="llm-status">
      <span :class="['dot', config?.configured ? 'ok' : 'bad']"></span>
      <div>
        <strong>{{ config?.configured ? '已配置' : '未配置' }}</strong>
        <p>{{ config?.model || '配置后才允许诊断' }}</p>
      </div>
    </div>

    <form class="config-form" @submit.prevent="submit">
      <label>
        <span>Base URL</span>
        <input v-model="form.base_url" placeholder="https://api.deepseek.com/v1" />
      </label>
      <label>
        <span>Model</span>
        <input v-model="form.model" placeholder="deepseek-chat" />
      </label>
      <label>
        <span>API Key</span>
        <input v-model="form.api_key" type="password" placeholder="不会回显，留空表示不修改" />
      </label>
      <div class="form-row">
        <label>
          <span>JSON</span>
          <select v-model="form.json_mode">
            <option :value="true">开启</option>
            <option :value="false">关闭</option>
          </select>
        </label>
        <label>
          <span>Timeout</span>
          <input v-model.number="form.timeout_seconds" type="number" min="1" max="300" />
        </label>
      </div>
      <button type="submit" :disabled="loading">保存配置</button>
    </form>
  </UiPanel>
</template>

<script setup>
import { reactive, watch } from 'vue';
import UiPanel from './ui/UiPanel.vue';

const props = defineProps({
  config: Object,
  loading: Boolean,
});

const emit = defineEmits(['save']);

const form = reactive({
  base_url: '',
  model: '',
  api_key: '',
  json_mode: true,
  timeout_seconds: 60,
});

watch(
  () => props.config,
  (config) => {
    if (!config) {
      return;
    }
    form.base_url = config.base_url || form.base_url;
    form.model = config.model || form.model;
    form.json_mode = config.json_mode ?? true;
    form.timeout_seconds = config.timeout_seconds || 60;
  },
  { immediate: true }
);

function submit() {
  emit('save', {
    base_url: form.base_url,
    model: form.model,
    api_key: form.api_key,
    json_mode: form.json_mode,
    timeout_seconds: form.timeout_seconds,
  });
  form.api_key = '';
}
</script>

<style scoped>
.llm-status {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  margin-bottom: 12px;
}

.llm-status p {
  margin: 4px 0 0;
  color: var(--nx-text-dim);
  word-break: break-word;
}

.dot {
  width: 10px;
  height: 10px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--nx-danger);
}

.dot.ok {
  background: var(--nx-success);
}

.config-form {
  display: grid;
  gap: 10px;
}

label {
  display: grid;
  gap: 5px;
}

label span {
  color: var(--nx-text-dim);
  font-size: 12px;
  font-weight: 700;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

</style>
