<template>
  <UiPanel title="厂商设备采集">
    <div class="discovery-status">
      <span :class="['dot', hasDiscoverySource ? 'ok' : 'bad']"></span>
      <div>
        <strong>{{ hasDiscoverySource ? '已配置采集入口' : '未配置采集入口' }}</strong>
        <p>{{ statusText }}</p>
      </div>
    </div>

    <form class="config-form" @submit.prevent="submit">
      <div class="form-row">
        <label>
          <span>厂商</span>
          <select v-model="form.profile_id">
            <option value="snmp_lldp">通用 SNMP 设备</option>
            <option value="h3c_snmp_lldp">H3C 设备</option>
          </select>
        </label>
        <label>
          <span>SNMP Community</span>
          <input v-model="form.community" placeholder="public" />
        </label>
      </div>

      <label>
        <span>管理网段 CIDR</span>
        <textarea
          v-model="form.scan_cidrs"
          rows="3"
          placeholder="192.168.10.0/24&#10;10.10.0.0/24"
        />
      </label>

      <label>
        <span>Seed IP / 主机名</span>
        <textarea
          v-model="form.targets"
          rows="3"
          placeholder="可选；填写后优先采集这些设备&#10;192.168.10.11&#10;192.168.10.12"
        />
      </label>

      <div class="actions-row">
        <button class="secondary" type="button" :disabled="loading" @click="applyFrrPreset">填入 FRR 实验设备</button>
        <button type="submit" :disabled="loading">保存配置</button>
      </div>
    </form>
  </UiPanel>
</template>

<script setup>
import { computed, reactive, watch } from 'vue';
import UiPanel from './ui/UiPanel.vue';

const props = defineProps({
  config: Object,
  loading: Boolean,
});

const emit = defineEmits(['save']);

const form = reactive({
  profile_id: 'snmp_lldp',
  community: 'public',
  scan_cidrs: '',
  targets: '',
});

const hasDiscoverySource = computed(() => Boolean(listFromText(form.scan_cidrs).length || listFromText(form.targets).length));
const statusText = computed(() => {
  const cidrCount = listFromText(form.scan_cidrs).length;
  const targetCount = listFromText(form.targets).length;
  if (cidrCount && targetCount) {
    return `${cidrCount} 个管理网段，${targetCount} 个 seed IP。`;
  }
  if (cidrCount) {
    return `${cidrCount} 个管理网段，采集时后端会主动读取设备 MIB。`;
  }
  if (targetCount) {
    return `${targetCount} 个 seed IP，采集时后端会直接读取设备 MIB。`;
  }
  return '填写管理网段或 seed IP 后，系统会按所选厂商采集设备 MIB。';
});

watch(
  () => props.config,
  (config) => {
    if (!config) {
      return;
    }
    form.profile_id = config.profile_id || 'snmp_lldp';
    form.community = config.community || 'public';
    form.scan_cidrs = (config.scan_cidrs || []).join('\n');
    form.targets = (config.targets || []).join('\n');
  },
  { immediate: true }
);

function submit() {
  emit('save', {
    profile_id: form.profile_id,
    community: form.community,
    scan_enabled: true,
    scan_cidrs: listFromText(form.scan_cidrs),
    targets: listFromText(form.targets),
    timeout_seconds: 3,
    scan_timeout_seconds: 1.5,
    scan_concurrency: 12,
    max_scan_hosts: 256,
  });
}

function applyFrrPreset() {
  form.profile_id = 'snmp_lldp';
  form.community = 'public';
  form.scan_cidrs = '';
  form.targets = ['127.0.0.1:11611', '127.0.0.1:11612', '127.0.0.1:11613', '127.0.0.1:11614'].join('\n');
}

function listFromText(value) {
  return String(value || '')
    .replace(/[,;]/g, '\n')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
}
</script>

<style scoped>
.discovery-status {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  margin-bottom: 12px;
}

.discovery-status p {
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

.actions-row {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 760px) {
  .form-row {
    grid-template-columns: 1fr;
  }

  .actions-row {
    flex-direction: column;
  }
}
</style>
