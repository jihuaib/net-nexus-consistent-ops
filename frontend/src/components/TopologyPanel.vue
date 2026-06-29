<template>
  <UiPanel class="topology-panel-shell" title="拓扑发现">
    <template #actions>
      <div class="discover-actions">
        <select
          class="group-select"
          :value="selectedGroupId"
          :disabled="loading || groupOptions.length <= 1"
          title="选择组网"
          @change="$emit('select-group', $event.target.value)"
        >
          <option v-for="group in groupOptions" :key="group.id" :value="group.id">
            {{ group.label }}
          </option>
        </select>
        <button class="secondary" @click="$emit('discover', { mode: 'snmp_lldp' })" :disabled="loading">
          <Play :size="15" />
          <span>采集</span>
        </button>
      </div>
    </template>

    <div class="topology-panel">
      <div class="topology-summary">
        <div>
          <span>设备</span>
          <strong>{{ visibleNodeCount }}</strong>
        </div>
        <div>
          <span>链路</span>
          <strong>{{ visibleEdgeCount }}</strong>
        </div>
        <div>
          <span>组网</span>
          <strong>{{ selectedGroupLabel }}</strong>
        </div>
      </div>

      <TopologyGraph :topology="visibleTopology" />
    </div>
  </UiPanel>
</template>

<script setup>
import { computed } from 'vue';
import { Play } from '@lucide/vue';
import TopologyGraph from './TopologyGraph.vue';
import UiPanel from './ui/UiPanel.vue';

const props = defineProps({
  topology: Object,
  selectedGroupId: {
    type: String,
    default: 'all',
  },
  capabilities: Object,
  loading: Boolean,
});

defineEmits(['discover', 'select-group']);

const groups = computed(() => props.topology?.groups || []);
const groupOptions = computed(() => [
  {
    id: 'all',
    label: groups.value.length > 1 ? `全部组网 (${groups.value.length})` : '全部组网',
  },
  ...groups.value.map((group) => ({
    id: group.id,
    label: `${group.name} (${group.node_count || group.nodes?.length || 0})`,
  })),
]);
const selectedGroup = computed(() => groups.value.find((group) => group.id === props.selectedGroupId) || null);
const selectedGroupLabel = computed(() => selectedGroup.value?.name || '全部');
const visibleTopology = computed(() => filterTopologyByGroup(props.topology, selectedGroup.value));
const visibleNodeCount = computed(() => visibleTopology.value?.nodes?.length || 0);
const visibleEdgeCount = computed(() => visibleTopology.value?.edges?.length || 0);
function filterTopologyByGroup(topology, group) {
  if (!topology || !group) {
    return topology;
  }
  const groupNodeIds = new Set(group.nodes || []);
  const groupEdgeIds = new Set(group.edges || []);
  const nodes = (topology.nodes || []).filter((node) => groupNodeIds.has(node.id));
  const edges = (topology.edges || []).filter(
    (edge) => groupEdgeIds.has(edgeIdentity(edge)) || (groupNodeIds.has(edge.source) && groupNodeIds.has(edge.target))
  );
  return {
    ...topology,
    id: `${topology.id || 'topology'}-${group.id}`,
    name: group.name,
    nodes,
    edges,
    groups: [group],
    discovery: {
      ...(topology.discovery || {}),
      node_count: nodes.length,
      edge_count: edges.length,
      selected_group_id: group.id,
      selected_group_name: group.name,
    },
  };
}

function edgeIdentity(edge) {
  return [
    edge.source || '',
    edge.target || '',
    edge.source_interface || '',
    edge.target_interface || '',
    edge.protocol || '',
  ].join('|');
}
</script>

<style scoped>
.topology-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
}

.topology-panel-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.topology-panel :deep(.topology-graph) {
  height: 100%;
  min-height: 0;
}

.discover-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

.discover-actions select {
  width: 132px;
  min-width: 132px;
  height: 32px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 0 30px 0 10px;
  color: var(--nx-text);
  background: var(--nx-surface-2);
  font: inherit;
}

.discover-actions .group-select {
  width: 160px;
  min-width: 160px;
}

.discover-actions button {
  flex: 0 0 auto;
  min-width: 72px;
  white-space: nowrap;
}

.topology-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.topology-summary div {
  display: grid;
  gap: 4px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.topology-summary span {
  color: var(--nx-text-dim);
}

.topology-summary strong {
  color: var(--nx-text);
  font-size: 18px;
}

@media (max-width: 640px) {
  .topology-summary {
    grid-template-columns: 1fr;
  }

  .discover-actions {
    width: 100%;
  }

  .discover-actions select {
    flex: 1 1 auto;
    min-width: 0;
  }

  .discover-actions .group-select {
    width: 100%;
  }
}
</style>
