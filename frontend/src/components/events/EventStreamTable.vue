<template>
  <UiPanel :title="title">
    <div v-if="events.length" class="event-list">
      <article v-for="event in events" :key="event.event_id" class="event-item">
        <header>
          <span class="tag">{{ event.channel }}</span>
          <strong>{{ event.event_type }}</strong>
          <small>{{ formatTime(event.timestamp) }}</small>
        </header>
        <div class="event-meta">
          <span>{{ event.device_id }}</span>
          <span>{{ event.object }}</span>
          <span>{{ event.severity }}</span>
          <span>{{ event.source_ip || '-' }}</span>
        </div>
        <p>{{ event.message || event.raw }}</p>
        <details v-if="hasAttributes(event)">
          <summary>属性</summary>
          <pre>{{ JSON.stringify(event.attributes, null, 2) }}</pre>
        </details>
      </article>
    </div>
    <p v-else class="empty">{{ emptyText }}</p>
  </UiPanel>
</template>

<script setup>
import UiPanel from '../ui/UiPanel.vue';

defineProps({
  title: {
    type: String,
    default: '事件列表',
  },
  events: {
    type: Array,
    default: () => [],
  },
  emptyText: {
    type: String,
    default: '还没有收到这类上报事件。',
  },
});

function hasAttributes(event) {
  return event.attributes && Object.keys(event.attributes).length > 0;
}

function formatTime(value) {
  if (!value) {
    return '-';
  }
  return new Date(value).toLocaleString();
}
</script>

<style scoped>
.event-list {
  display: grid;
  gap: 10px;
}

.event-item {
  display: grid;
  gap: 8px;
  min-width: 0;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.event-item header,
.event-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.event-item header strong,
.event-item p {
  min-width: 0;
  overflow-wrap: anywhere;
}

.event-item small,
.event-meta,
.empty {
  color: var(--nx-text-dim);
}

.event-meta {
  flex-wrap: wrap;
}

.event-item p {
  margin: 0;
  line-height: 1.5;
}

.tag {
  flex: 0 0 auto;
  border: 1px solid var(--nx-accent-border-soft);
  border-radius: 999px;
  padding: 2px 7px;
  color: var(--nx-accent);
  background: var(--nx-accent-softer);
  font-size: 11px;
  font-weight: 700;
}

details {
  border-top: 1px solid var(--nx-border-muted);
  padding-top: 6px;
}

summary {
  color: var(--nx-text-dim);
  cursor: pointer;
}

pre {
  max-height: 260px;
  overflow: auto;
  margin: 8px 0 0;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-surface);
  font-family: var(--nx-font-mono);
  font-size: 11px;
  white-space: pre-wrap;
}
</style>
