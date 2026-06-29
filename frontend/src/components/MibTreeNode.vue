<template>
  <li class="mib-node">
    <details :open="isOpen(node, depth)">
      <summary :class="{ highlighted: isHighlighted(node) }" :data-oid="node.oid">
        <span :class="['node-kind', isBranch(node) ? 'branch' : 'leaf']" aria-hidden="true">
          <ChevronRight v-if="isBranch(node)" :size="13" :stroke-width="2.2" />
          <Circle v-else :size="8" :stroke-width="2.4" />
        </span>
        <span class="node-title">{{ node.objectName || node.title || node.oid }}</span>
        <code>{{ node.oid }}</code>
        <span class="node-tail">
          <small>{{ node.moduleName || 'unknown' }}</small>
          <small>{{ node.macro || 'OBJECT' }}</small>
          <small v-if="node.syntax">{{ node.syntax }}</small>
          <small v-if="node.maxAccess">{{ node.maxAccess }}</small>
          <small v-if="node.childCount">{{ node.childCount }} children</small>
        </span>
      </summary>

      <p v-if="node.description" class="node-description">{{ node.description }}</p>

      <ul v-if="node.children?.length" class="mib-children">
        <MibTreeNode
          v-for="child in node.children"
          :key="child.oid"
          :node="child"
          :depth="depth + 1"
          :expanded-oids="expandedOids"
          :highlighted-oid="highlightedOid"
        />
      </ul>
    </details>
  </li>
</template>

<script setup>
import { ChevronRight, Circle } from '@lucide/vue';

defineOptions({ name: 'MibTreeNode' });

const props = defineProps({
  node: {
    type: Object,
    required: true,
  },
  depth: {
    type: Number,
    default: 0,
  },
  expandedOids: {
    type: Object,
    default: () => new Set(),
  },
  highlightedOid: {
    type: String,
    default: '',
  },
});

function isBranch(node) {
  return Boolean(Number(node?.childCount || 0) || node?.children?.length);
}

function isOpen(node, depth) {
  return depth < 2 || props.expandedOids.has(node?.oid);
}

function isHighlighted(node) {
  return Boolean(props.highlightedOid && node?.oid === props.highlightedOid);
}
</script>

<style scoped>
.mib-node {
  list-style: none;
}

.mib-node details {
  border-left: 1px solid var(--nx-border);
  padding-left: 10px;
}

.mib-node summary {
  display: grid;
  grid-template-columns: 16px minmax(130px, max-content) max-content minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  min-width: max-content;
  min-height: 30px;
  cursor: pointer;
  list-style: none;
  white-space: nowrap;
}

.mib-node summary.highlighted {
  border-radius: 6px;
  background: var(--nx-accent-softer);
  box-shadow: inset 0 0 0 1px var(--nx-accent-border-soft);
}

.mib-node summary::-webkit-details-marker {
  display: none;
}

.node-kind {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  color: var(--nx-text-dim);
}

.mib-node details[open] > summary .node-kind.branch svg {
  transform: rotate(90deg);
}

.node-kind svg {
  transition: transform 0.14s ease;
}

.node-kind.leaf {
  color: var(--nx-border-soft);
}

.node-title {
  color: var(--nx-text);
  font-weight: 700;
}

.node-tail {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

code {
  border: 1px solid var(--nx-border);
  border-radius: 5px;
  padding: 2px 5px;
  color: var(--nx-accent);
  background: var(--nx-surface-2);
  font-size: 12px;
}

small,
.node-description {
  color: var(--nx-text-dim);
}

small {
  border: 1px solid var(--nx-border);
  border-radius: 5px;
  padding: 2px 6px;
  background: var(--nx-surface-2);
  font-size: 11px;
}

.node-description {
  max-width: 980px;
  margin: 3px 0 8px 24px;
  font-size: 12px;
  line-height: 1.5;
}

.mib-children {
  display: grid;
  gap: 4px;
  margin: 0 0 0 12px;
  padding: 0;
}
</style>
