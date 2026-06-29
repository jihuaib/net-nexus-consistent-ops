<template>
  <section class="table-shell">
    <header class="table-head">
      <div>
        <h2>{{ title }}</h2>
        <span>{{ events.length }} 条匹配事件</span>
      </div>
    </header>
    <div v-if="events.length" class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>级别</th>
            <th>时间</th>
            <th>设备</th>
            <th>对象</th>
            <th>事件类型</th>
            <th>来源</th>
            <th>摘要</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="event in events"
            :key="event.event_id"
            :class="{ selected: selectedId === event.event_id }"
            @click="$emit('select', event)"
          >
            <td>
              <span class="severity" :class="severityClass(event.severity)">{{ event.severity || 'info' }}</span>
            </td>
            <td class="time-cell">{{ formatTime(event.timestamp) }}</td>
            <td>{{ event.device_id || '-' }}</td>
            <td>{{ event.object || '-' }}</td>
            <td><code>{{ event.event_type }}</code></td>
            <td>{{ event.source_ip || '-' }}</td>
            <td class="message-cell">{{ event.message || event.raw || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="empty">{{ emptyText }}</p>
  </section>
</template>

<script setup>
defineProps({
  title: {
    type: String,
    default: '事件流水',
  },
  events: {
    type: Array,
    default: () => [],
  },
  selectedId: {
    type: String,
    default: '',
  },
  emptyText: {
    type: String,
    default: '当前条件下没有事件。',
  },
});

defineEmits(['select']);

function severityClass(value) {
  return String(value || 'info').toLowerCase();
}

function formatTime(value) {
  if (!value) {
    return '-';
  }
  return new Date(value).toLocaleString();
}
</script>

<style scoped>
.table-shell {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  background: var(--nx-surface-raised);
}

.table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 45px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--nx-border);
}

.table-head h2 {
  margin: 0;
  font-size: 13px;
}

.table-head span,
.empty {
  color: var(--nx-text-dim);
}

.table-scroll {
  max-height: calc(100vh - 340px);
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 12px;
}

th,
td {
  min-width: 0;
  border-bottom: 1px solid var(--nx-border-muted);
  padding: 8px 9px;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  color: var(--nx-text-dim);
  background: var(--nx-surface-2);
  font-weight: 700;
}

tbody tr {
  cursor: pointer;
}

tbody tr:hover,
tbody tr.selected {
  background: var(--nx-accent-softer);
}

th:nth-child(1),
td:nth-child(1) {
  width: 82px;
}

th:nth-child(2),
td:nth-child(2) {
  width: 142px;
}

th:nth-child(3),
td:nth-child(3),
th:nth-child(4),
td:nth-child(4) {
  width: 105px;
}

th:nth-child(5),
td:nth-child(5) {
  width: 185px;
}

th:nth-child(6),
td:nth-child(6) {
  width: 105px;
}

.message-cell {
  min-width: 220px;
}

.severity {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 58px;
  height: 22px;
  border: 1px solid var(--nx-border);
  border-radius: 999px;
  padding: 0 7px;
  color: var(--nx-text-dim);
  background: var(--nx-bg);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.severity.critical {
  border-color: var(--nx-danger-border);
  color: var(--nx-danger);
  background: var(--nx-danger-soft);
}

.severity.major,
.severity.warning {
  border-color: rgba(183, 121, 31, 0.42);
  color: var(--nx-warning);
  background: var(--nx-warning-soft);
}

.severity.info {
  border-color: var(--nx-border);
  color: var(--nx-text-dim);
  background: var(--nx-surface-2);
}

.empty {
  margin: 0;
  padding: 18px 12px;
}

@media (max-width: 900px) {
  .table-scroll {
    max-height: none;
  }
}
</style>
