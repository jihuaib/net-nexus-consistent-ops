<template>
  <div ref="graphRef" class="topology-graph" @click="clearSelection">
    <div class="zoom-controls" @click.stop>
      <button type="button" title="缩小" :disabled="zoom <= MIN_ZOOM" @click="zoomOut">
        <ZoomOut :size="14" :stroke-width="2" />
      </button>
      <span>{{ zoomPercent }}</span>
      <button type="button" title="放大" :disabled="zoom >= MAX_ZOOM" @click="zoomIn">
        <ZoomIn :size="14" :stroke-width="2" />
      </button>
      <button type="button" title="重置缩放" :disabled="zoom === 1" @click="resetZoom">
        <RotateCcw :size="14" :stroke-width="2" />
      </button>
    </div>

    <div class="graph-canvas" :style="canvasStyle">
      <svg class="edge-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <g v-for="edge in drawableEdges" :key="edge.key">
          <line
            :x1="edge.source.x"
            :y1="edge.source.y"
            :x2="edge.target.x"
            :y2="edge.target.y"
            class="edge-hit"
            @click.stop="selectEdge(edge.raw)"
          />
          <line
            :x1="edge.source.x"
            :y1="edge.source.y"
            :x2="edge.target.x"
            :y2="edge.target.y"
            :class="['edge-line', edge.status, { selected: isSelectedEdge(edge.raw) }]"
          />
        </g>
      </svg>

      <span
        v-for="edge in drawableEdges"
        :key="`${edge.key}-label`"
        class="edge-label"
        :class="{ selected: isSelectedEdge(edge.raw) }"
        :style="{ left: `${edge.label.x}%`, top: `${edge.label.y}%` }"
      >
        {{ edge.label.text }}
      </span>

      <article
        v-for="node in positionedNodes"
        :key="node.id"
        class="graph-node"
        :class="[
          node.role || 'unknown',
          statusClass(node.status),
          { dragging: draggingNodeId === node.id, selected: isSelectedNode(node) },
        ]"
        :style="{ left: `${node.x}%`, top: `${node.y}%` }"
        @pointerdown="startNodeDrag($event, node)"
        @click.stop="selectNode(node)"
      >
        <span class="node-icon">
          <component :is="nodeIcon(node)" :size="18" :stroke-width="2.2" />
        </span>
        <strong>{{ node.label || node.name || node.id }}</strong>
        <small>{{ node.management_ip || node.role || 'unknown' }}</small>
      </article>
    </div>

    <aside v-if="selectedItem" class="selection-card">
      <template v-if="selectedItem.type === 'node'">
        <span class="selection-eyebrow">{{ selectedItem.node.role || 'device' }}</span>
        <strong>{{ nodeTitle(selectedItem.node) }}</strong>
        <dl>
          <div>
            <dt>管理地址</dt>
            <dd>{{ selectedItem.node.management_ip || '--' }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{{ selectedItem.node.status || 'unknown' }}</dd>
          </div>
          <div>
            <dt>设备 ID</dt>
            <dd>{{ selectedItem.node.id }}</dd>
          </div>
        </dl>
      </template>

      <template v-else>
        <span class="selection-eyebrow">link</span>
        <strong>{{ nodeLabel(selectedItem.edge.source) }} -> {{ nodeLabel(selectedItem.edge.target) }}</strong>
        <dl>
          <div>
            <dt>接口</dt>
            <dd>{{ edgeLabel(selectedItem.edge) }}</dd>
          </div>
          <div>
            <dt>协议</dt>
            <dd>{{ selectedItem.edge.protocol || 'unknown' }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{{ selectedItem.edge.status || 'unknown' }}</dd>
          </div>
        </dl>
      </template>
    </aside>

    <div v-if="!positionedNodes.length" class="empty-graph">
      <Network :size="28" />
      <span>未发现拓扑</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, reactive, ref, watch } from 'vue';
import { Cpu, Network, RotateCcw, Router, Server, ZoomIn, ZoomOut } from '@lucide/vue';

const props = defineProps({
  topology: Object,
});

const MIN_ZOOM = 0.65;
const MAX_ZOOM = 1.8;
const ZOOM_STEP = 0.15;

const graphRef = ref(null);
const manualPositions = reactive({});
const draggingNodeId = ref('');
const selectedItem = ref(null);
const zoom = ref(1);
let dragState = null;

const nodes = computed(() => props.topology?.nodes || []);
const edges = computed(() => props.topology?.edges || []);
const groups = computed(() => props.topology?.groups || []);
const autoLayoutNodes = computed(() => layoutNodes(nodes.value, groups.value));
const positionedNodes = computed(() =>
  autoLayoutNodes.value.map((node) => ({
    ...node,
    ...(manualPositions[node.id] || {}),
  }))
);
const positionById = computed(() => new Map(positionedNodes.value.map((node) => [node.id, node])));
const nodeById = computed(() => new Map(nodes.value.map((node) => [node.id, node])));
const zoomPercent = computed(() => `${Math.round(zoom.value * 100)}%`);
const canvasStyle = computed(() => ({
  transform: `scale(${zoom.value})`,
}));
const drawableEdges = computed(() =>
  edges.value
    .map((edge) => {
      const source = positionById.value.get(edge.source);
      const target = positionById.value.get(edge.target);
      if (!source || !target) {
        return null;
      }
      const labelText = edgeLabel(edge);
      const midX = (source.x + target.x) / 2;
      const midY = (source.y + target.y) / 2;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const length = Math.hypot(dx, dy) || 1;
      const labelOffset = 4;
      return {
        key: `${edge.source}-${edge.target}-${edge.source_interface || 'source'}-${edge.target_interface || 'target'}`,
        source,
        target,
        status: edge.status || 'unknown',
        label: {
          x: clamp(midX + (-dy / length) * labelOffset, 10, 90),
          y: clamp(midY + (dx / length) * labelOffset, 10, 90),
          text: labelText,
        },
        raw: edge,
      };
    })
    .filter(Boolean)
);

watch(
  nodes,
  (nextNodes) => {
    const nextIds = new Set(nextNodes.map((node) => node.id));
    for (const id of Object.keys(manualPositions)) {
      if (!nextIds.has(id)) {
        delete manualPositions[id];
      }
    }
    if (selectedItem.value?.type === 'node' && !nextIds.has(selectedItem.value.node.id)) {
      selectedItem.value = null;
    }
  },
  { deep: true }
);

watch(
  edges,
  (nextEdges) => {
    if (selectedItem.value?.type !== 'edge') {
      return;
    }
    const selectedKey = edgeIdentity(selectedItem.value.edge);
    if (!nextEdges.some((edge) => edgeIdentity(edge) === selectedKey)) {
      selectedItem.value = null;
    }
  },
  { deep: true }
);

function layoutNodes(rawNodes, rawGroups = []) {
  if (rawGroups.length > 1) {
    return layoutGroupedNodes(rawNodes, rawGroups);
  }
  return baseLayoutNodes(rawNodes);
}

function baseLayoutNodes(rawNodes) {
  if (!rawNodes.length) {
    return [];
  }
  if (rawNodes.length === 1) {
    return [{ ...rawNodes[0], x: 50, y: 50 }];
  }

  const spines = rawNodes.filter((node) => normalizeRole(node.role) === 'spine');
  const leaves = rawNodes.filter((node) => normalizeRole(node.role) === 'leaf');
  const others = rawNodes.filter((node) => !['spine', 'leaf'].includes(normalizeRole(node.role)));

  if (spines.length || leaves.length) {
    return [
      ...rowLayout(spines, 26),
      ...rowLayout(others, 50),
      ...rowLayout(leaves, 74),
    ];
  }

  return rawNodes.map((node, index) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * index) / rawNodes.length;
    return {
      ...node,
      x: 50 + 34 * Math.cos(angle),
      y: 50 + 30 * Math.sin(angle),
    };
  });
}

function layoutGroupedNodes(rawNodes, rawGroups) {
  const nodeById = new Map(rawNodes.map((node) => [node.id, node]));
  const visibleGroups = rawGroups
    .map((group) => ({
      ...group,
      nodes: (group.nodes || []).map((nodeId) => nodeById.get(nodeId)).filter(Boolean),
    }))
    .filter((group) => group.nodes.length);

  if (!visibleGroups.length) {
    return baseLayoutNodes(rawNodes);
  }

  const columns = Math.min(visibleGroups.length, 2);
  const rows = Math.ceil(visibleGroups.length / columns);
  const positioned = [];

  visibleGroups.forEach((group, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const xStart = column * (100 / columns);
    const yStart = row * (100 / rows);
    const xMin = xStart + 8;
    const xMax = xStart + 100 / columns - 8;
    const yMin = yStart + 14;
    const yMax = yStart + 100 / rows - 14;
    const localNodes = baseLayoutNodes(group.nodes);

    positioned.push(
      ...localNodes.map((node) => ({
        ...node,
        topology_group_id: group.id,
        topology_group_name: group.name,
        x: xMin + (node.x / 100) * Math.max(xMax - xMin, 1),
        y: yMin + (node.y / 100) * Math.max(yMax - yMin, 1),
      }))
    );
  });

  return positioned;
}

function rowLayout(items, y) {
  if (!items.length) {
    return [];
  }
  const gap = 76 / Math.max(items.length, 1);
  return items.map((node, index) => ({
    ...node,
    x: 12 + gap / 2 + index * gap,
    y,
  }));
}

function normalizeRole(role) {
  return String(role || '').toLowerCase();
}

function nodeIcon(node) {
  const role = normalizeRole(node.role);
  if (role === 'spine' || role === 'router') {
    return Router;
  }
  if (role === 'leaf') {
    return Server;
  }
  return Cpu;
}

function statusClass(status) {
  if (status === 'down' || status === 'critical') {
    return 'down';
  }
  if (status === 'up' || status === 'normal') {
    return 'up';
  }
  return 'unknown';
}

function edgeLabel(edge) {
  const left = edge.source_interface || '--';
  const right = edge.target_interface || '--';
  return `${left} / ${right}`;
}

function nodeTitle(node) {
  return node.label || node.name || node.id;
}

function nodeLabel(id) {
  const node = nodeById.value.get(id);
  return nodeTitle(node || { id });
}

function selectNode(node) {
  selectedItem.value = { type: 'node', node };
}

function selectEdge(edge) {
  if (draggingNodeId.value) {
    return;
  }
  selectedItem.value = { type: 'edge', edge };
}

function clearSelection() {
  if (!draggingNodeId.value) {
    selectedItem.value = null;
  }
}

function isSelectedNode(node) {
  return selectedItem.value?.type === 'node' && selectedItem.value.node.id === node.id;
}

function isSelectedEdge(edge) {
  return selectedItem.value?.type === 'edge' && edgeIdentity(selectedItem.value.edge) === edgeIdentity(edge);
}

function edgeIdentity(edge) {
  return [
    edge.source,
    edge.target,
    edge.source_interface || '',
    edge.target_interface || '',
    edge.protocol || '',
  ].join('|');
}

function zoomIn() {
  zoom.value = clampZoom(zoom.value + ZOOM_STEP);
}

function zoomOut() {
  zoom.value = clampZoom(zoom.value - ZOOM_STEP);
}

function resetZoom() {
  zoom.value = 1;
}

function clampZoom(value) {
  return Math.round(clamp(value, MIN_ZOOM, MAX_ZOOM) * 100) / 100;
}

function pointToPercent(event) {
  const rect = graphRef.value?.getBoundingClientRect();
  if (!rect) {
    return { x: 50, y: 50 };
  }
  const scale = zoom.value || 1;
  const logicalX = rect.width / 2 + (event.clientX - rect.left - rect.width / 2) / scale;
  const logicalY = rect.height / 2 + (event.clientY - rect.top - rect.height / 2) / scale;
  return {
    x: clamp((logicalX / rect.width) * 100, 8, 92),
    y: clamp((logicalY / rect.height) * 100, 12, 88),
  };
}

function startNodeDrag(event, node) {
  if (event.button !== 0 || !graphRef.value) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  const current = pointToPercent(event);
  dragState = {
    nodeId: node.id,
    pointerId: event.pointerId,
    startPointer: current,
    startPosition: { x: node.x, y: node.y },
  };
  draggingNodeId.value = node.id;
  selectedItem.value = { type: 'node', node };
  event.currentTarget?.setPointerCapture?.(event.pointerId);
  window.addEventListener('pointermove', moveNodeDrag);
  window.addEventListener('pointerup', stopNodeDrag);
  window.addEventListener('pointercancel', stopNodeDrag);
}

function moveNodeDrag(event) {
  if (!dragState) {
    return;
  }
  const current = pointToPercent(event);
  manualPositions[dragState.nodeId] = {
    x: clamp(dragState.startPosition.x + current.x - dragState.startPointer.x, 8, 92),
    y: clamp(dragState.startPosition.y + current.y - dragState.startPointer.y, 12, 88),
  };
}

function stopNodeDrag() {
  dragState = null;
  draggingNodeId.value = '';
  window.removeEventListener('pointermove', moveNodeDrag);
  window.removeEventListener('pointerup', stopNodeDrag);
  window.removeEventListener('pointercancel', stopNodeDrag);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

onUnmounted(() => {
  stopNodeDrag();
});
</script>

<style scoped>
.topology-graph {
  position: relative;
  min-height: 390px;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  background:
    linear-gradient(90deg, rgba(105, 114, 129, 0.13) 1px, transparent 1px),
    linear-gradient(rgba(105, 114, 129, 0.13) 1px, transparent 1px),
    var(--nx-bg);
  background-size: 32px 32px;
  overflow: hidden;
}

.graph-canvas {
  position: absolute;
  inset: 0;
  transform-origin: 50% 50%;
  transition: transform 160ms ease;
}

.zoom-controls {
  position: absolute;
  z-index: 6;
  top: 10px;
  left: 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  padding: 3px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 10px 24px rgba(37, 42, 50, 0.14);
}

.zoom-controls button {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  min-height: 26px;
  border-color: transparent;
  border-radius: 6px;
  padding: 0;
  color: var(--nx-icon);
  background: transparent;
}

.zoom-controls button:hover:not(:disabled) {
  border-color: var(--nx-accent-border);
  color: var(--nx-accent);
  background: var(--nx-accent-soft);
}

.zoom-controls button:disabled {
  opacity: 0.42;
}

.zoom-controls span {
  min-width: 42px;
  color: var(--nx-text-dim);
  font-size: 11px;
  font-weight: 700;
  text-align: center;
}

.edge-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.edge-hit {
  stroke: transparent;
  stroke-width: 5;
  pointer-events: stroke;
}

.edge-line {
  stroke: var(--nx-text-dim);
  stroke-width: 0.35;
  stroke-linecap: round;
  opacity: 0.82;
  pointer-events: none;
}

.edge-line.up {
  stroke: var(--nx-success);
}

.edge-line.down {
  stroke: var(--nx-danger);
  stroke-dasharray: 3 2;
}

.edge-line.selected {
  stroke: var(--nx-accent);
  stroke-width: 0.65;
  opacity: 1;
}

.edge-label {
  position: absolute;
  z-index: 1;
  max-width: 104px;
  border: 1px solid var(--nx-border-soft);
  border-radius: 999px;
  padding: 1px 6px;
  color: var(--nx-text-dim);
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 3px 10px rgba(37, 42, 50, 0.08);
  font-size: 10px;
  font-weight: 600;
  line-height: 1.35;
  letter-spacing: 0;
  overflow: hidden;
  pointer-events: none;
  text-overflow: ellipsis;
  transform: translate(-50%, -50%);
  white-space: nowrap;
}

.edge-label.selected {
  border-color: var(--nx-accent-border);
  color: var(--nx-accent);
  background: rgba(255, 247, 239, 0.94);
}

.graph-node {
  position: absolute;
  z-index: 1;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  grid-template-rows: auto auto;
  align-items: center;
  gap: 2px 9px;
  width: 172px;
  min-height: 58px;
  border: 1px solid var(--nx-border);
  border-left: 4px solid var(--nx-text-dim);
  border-radius: 7px;
  padding: 9px 10px;
  background: var(--nx-surface-raised);
  box-shadow: 0 10px 22px rgba(37, 42, 50, 0.12);
  cursor: grab;
  touch-action: none;
  transform: translate(-50%, -50%);
}

.graph-node:hover,
.graph-node.dragging,
.graph-node.selected {
  border-color: var(--nx-accent-border);
  box-shadow: 0 12px 28px rgba(37, 42, 50, 0.16);
}

.graph-node.selected {
  z-index: 2;
  outline: 2px solid var(--nx-accent-soft);
  outline-offset: 2px;
}

.graph-node.dragging {
  z-index: 3;
  cursor: grabbing;
}

.graph-node.up {
  border-left-color: var(--nx-success);
}

.graph-node.down {
  border-color: var(--nx-danger-border);
  border-left-color: var(--nx-danger);
  background: var(--nx-danger-soft);
}

.node-icon {
  grid-row: 1 / span 2;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  color: var(--nx-icon);
  background: var(--nx-accent-soft);
}

.graph-node.spine .node-icon,
.graph-node.router .node-icon {
  color: var(--nx-warning);
  background: var(--nx-warning-soft);
}

.graph-node.leaf .node-icon {
  color: var(--nx-icon);
  background: var(--nx-accent-soft);
}

.graph-node strong {
  min-width: 0;
  color: var(--nx-text);
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.graph-node small {
  min-width: 0;
  color: var(--nx-text-dim);
  overflow-wrap: anywhere;
}

.selection-card {
  position: absolute;
  z-index: 4;
  top: 12px;
  right: 12px;
  width: min(260px, calc(100% - 24px));
  border: 1px solid var(--nx-accent-border-soft);
  border-radius: 8px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 14px 34px rgba(37, 42, 50, 0.16);
  pointer-events: none;
}

.selection-card strong {
  display: block;
  margin-top: 4px;
  color: var(--nx-text);
  overflow-wrap: anywhere;
}

.selection-eyebrow {
  display: inline-flex;
  border: 1px solid var(--nx-accent-border-soft);
  border-radius: 6px;
  padding: 2px 6px;
  color: var(--nx-accent);
  background: var(--nx-accent-softer);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
}

.selection-card dl {
  display: grid;
  gap: 6px;
  margin: 10px 0 0;
}

.selection-card dl div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
}

.selection-card dt {
  color: var(--nx-text-dim);
}

.selection-card dd {
  margin: 0;
  color: var(--nx-text);
  overflow-wrap: anywhere;
}

.empty-graph {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  color: var(--nx-text-dim);
}

@media (max-width: 640px) {
  .topology-graph {
    min-height: 360px;
  }

  .graph-node {
    width: 148px;
  }
}
</style>
