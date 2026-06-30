<template>
  <div class="shell">
    <header class="titlebar">
      <div class="brand">
        <span class="brand__mark" aria-hidden="true">
          <Network :size="18" :stroke-width="2" />
        </span>
        <div class="brand__text">
          <strong>NetNexus ConsistentOps</strong>
          <span>AI Operations Console</span>
        </div>
      </div>

      <span class="spacer" />

      <button class="titlebar-button" type="button" title="刷新数据" :disabled="loading" @click="loadAll">
        <RefreshCw :size="16" :stroke-width="1.9" />
      </button>
      <button
        class="titlebar-button"
        :class="{ active: settingsOpen }"
        type="button"
        title="设置"
        @click="openSettings()"
      >
        <Settings :size="16" :stroke-width="1.9" />
      </button>
    </header>

    <div class="body">
      <AppSidebar
        :active-view="activeView"
        :loading="loading"
        :health="health"
        :llm-config="llmConfig"
        :topology="topology"
        @update:active-view="activeView = $event"
      />

      <main class="workspace">
        <div class="main-column">
          <DiagnosisView
            v-if="activeView === 'diagnosis'"
            v-model:input="input"
            :loading="loading"
            :session-id="sessionId"
            :session-records="sessionRecords"
            :messages="messages"
            :quick-prompts="quickPrompts"
            :diagnosis="diagnosis"
            :tool-trace="toolTrace"
            :consistency="consistency"
            :facts="facts"
            :topology="topology"
            :topology-group-id="topologyGroupId"
            :topology-capabilities="topologyCapabilities"
            :topology-discovery-config="topologyDiscoveryConfig"
            @send="sendMessage"
            @quick="sendQuick"
            @switch-session="switchSession"
            @restore-session="restoreSession"
            @reset-session="resetSession"
            @test-consistency="runConsistency"
            @discover-topology="discoverTopology"
            @select-topology-group="selectTopologyGroup"
            @configure-topology="openSettings('topology')"
            @apply-frr-topology-preset="applyFrrTopologyPreset"
            @apply-frr-bridge-topology-preset="applyFrrBridgeTopologyPreset"
            @refresh="loadAll"
          />

          <MibView v-else-if="activeView === 'mib'" />
          <KnowledgeView v-else-if="activeView === 'knowledge'" />
          <SyslogEventsView v-else-if="activeView === 'events-syslog'" />
          <TrapEventsView v-else-if="activeView === 'events-trap'" />
          <TelemetryEventsView v-else-if="activeView === 'events-telemetry'" />
        </div>
      </main>
    </div>

    <SettingsDialog
      v-if="settingsOpen"
      :loading="loading"
      :initial-category="settingsCategory"
      :llm-config="llmConfig"
      :topology-discovery-config="topologyDiscoveryConfig"
      @close="settingsOpen = false"
      @refresh="loadAll"
      @save-llm-config="saveConfig"
      @save-topology-config="saveTopologyConfig"
    />

    <AppAlerts />
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { Network, RefreshCw, Settings } from '@lucide/vue';
import AppAlerts from './components/AppAlerts.vue';
import AppSidebar from './components/AppSidebar.vue';
import SettingsDialog from './components/SettingsDialog.vue';
import { useAgentWorkspace } from './composables/useAgentWorkspace';
import DiagnosisView from './views/DiagnosisView.vue';
import KnowledgeView from './views/KnowledgeView.vue';
import MibView from './views/MibView.vue';
import SyslogEventsView from './views/events/SyslogEventsView.vue';
import TelemetryEventsView from './views/events/TelemetryEventsView.vue';
import TrapEventsView from './views/events/TrapEventsView.vue';

const activeView = ref('diagnosis');
const settingsOpen = ref(false);
const settingsCategory = ref('llm');

const {
  loading,
  sessionId,
  sessionRecords,
  input,
  health,
  llmConfig,
  topology,
  topologyGroupId,
  topologyCapabilities,
  topologyDiscoveryConfig,
  facts,
  diagnosis,
  consistency,
  toolTrace,
  messages,
  quickPrompts,
  loadAll,
  discoverTopology,
  selectTopologyGroup,
  sendMessage,
  sendQuick,
  switchSession,
  restoreSession,
  runConsistency,
  saveConfig,
  saveTopologyConfig,
  resetSession,
} = useAgentWorkspace();

function openSettings(category = 'llm') {
  settingsCategory.value = category;
  settingsOpen.value = true;
}

async function applyFrrTopologyPreset() {
  await saveTopologyConfig({
    profile_id: 'snmp_lldp',
    community: 'public',
    scan_enabled: true,
    scan_cidrs: [],
    targets: ['127.0.0.1:11611', '127.0.0.1:11612', '127.0.0.1:11613', '127.0.0.1:11614'],
    timeout_seconds: 3,
    scan_timeout_seconds: 1.5,
    scan_concurrency: 12,
    max_scan_hosts: 256,
  });
}

async function applyFrrBridgeTopologyPreset() {
  await saveTopologyConfig({
    profile_id: 'snmp_lldp',
    community: 'public',
    scan_enabled: true,
    scan_cidrs: [],
    targets: ['172.30.0.11', '172.30.0.12', '172.30.0.13', '172.30.0.14'],
    timeout_seconds: 3,
    scan_timeout_seconds: 1.5,
    scan_concurrency: 12,
    max_scan_hosts: 256,
  });
}

</script>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--nx-bg);
}

.titlebar {
  display: flex;
  align-items: center;
  height: 52px;
  flex: 0 0 52px;
  padding: 0 14px 0 16px;
  border-bottom: 1px solid var(--nx-border);
  background: var(--nx-titlebar-bg);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand__mark {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--nx-accent-border);
  border-radius: 8px;
  color: var(--nx-icon);
  background: var(--nx-accent-soft);
}

.brand__text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  line-height: 1.1;
}

.brand__text strong {
  overflow: hidden;
  color: var(--nx-text);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.brand__text span {
  color: var(--nx-text-dim);
  font-size: 11px;
}

.spacer {
  flex: 1;
}

.titlebar-button {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  min-height: 30px;
  margin-left: 6px;
  padding: 0;
  border-color: var(--nx-border);
  color: var(--nx-icon);
  background: var(--nx-surface-2);
}

.titlebar-button:hover,
.titlebar-button.active {
  border-color: var(--nx-accent-border);
  background: var(--nx-accent-soft);
}

.body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.workspace {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  padding: 8px;
  background: var(--nx-bg);
}

.main-column {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  background: var(--nx-surface);
  padding: 12px;
}

@media (max-width: 640px) {
  .brand__text span {
    display: none;
  }

  .main-column {
    padding: 8px;
  }
}
</style>
