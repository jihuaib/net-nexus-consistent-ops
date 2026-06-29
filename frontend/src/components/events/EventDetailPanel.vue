<template>
  <aside class="detail-panel">
    <header>
      <div>
        <h2>事件详情</h2>
        <span>{{ event ? event.event_id : '未选择' }}</span>
      </div>
    </header>

    <div v-if="event" class="detail-body">
      <section class="identity">
        <strong>{{ event.event_type }}</strong>
        <span class="severity" :class="severityClass(event.severity)">{{ event.severity || 'info' }}</span>
      </section>

      <dl class="detail-list">
        <div>
          <dt>设备</dt>
          <dd>{{ event.device_id || '-' }}</dd>
        </div>
        <div>
          <dt>对象</dt>
          <dd>{{ event.object || '-' }}</dd>
        </div>
        <div>
          <dt>通道</dt>
          <dd>{{ event.channel }}</dd>
        </div>
        <div>
          <dt>来源地址</dt>
          <dd>{{ event.source_ip || '-' }}</dd>
        </div>
        <div>
          <dt>事件时间</dt>
          <dd>{{ formatTime(event.timestamp) }}</dd>
        </div>
        <div>
          <dt>接收时间</dt>
          <dd>{{ formatTime(event.received_at) }}</dd>
        </div>
      </dl>

      <section>
        <h3>原始内容</h3>
        <p class="raw-text">{{ event.message || event.raw || '-' }}</p>
      </section>

      <section>
        <h3>归一化属性</h3>
        <pre>{{ JSON.stringify(event.attributes || {}, null, 2) }}</pre>
      </section>
    </div>

    <p v-else class="empty">选择一条事件查看原文、归一化字段和上报属性。</p>
  </aside>
</template>

<script setup>
defineProps({
  event: {
    type: Object,
    default: null,
  },
});

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
.detail-panel {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  background: var(--nx-surface-raised);
}

.detail-panel header {
  display: flex;
  align-items: center;
  min-height: 45px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--nx-border);
}

.detail-panel h2,
.detail-panel h3 {
  margin: 0;
  font-size: 13px;
}

.detail-panel header span,
.empty {
  color: var(--nx-text-dim);
}

.detail-body {
  display: grid;
  gap: 13px;
  max-height: calc(100vh - 340px);
  overflow: auto;
  padding: 12px;
}

.identity {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
}

.identity strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.severity {
  flex: 0 0 auto;
  border: 1px solid var(--nx-border);
  border-radius: 999px;
  padding: 3px 8px;
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

.detail-list {
  display: grid;
  gap: 8px;
  margin: 0;
}

.detail-list div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 9px;
  min-width: 0;
}

.detail-list dt {
  color: var(--nx-text-dim);
}

.detail-list dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
}

.raw-text,
pre {
  margin: 8px 0 0;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
  overflow-wrap: anywhere;
  line-height: 1.5;
}

pre {
  max-height: 260px;
  overflow: auto;
  font-family: var(--nx-font-mono);
  font-size: 11px;
  white-space: pre-wrap;
}

.empty {
  margin: 0;
  padding: 14px 12px;
  line-height: 1.5;
}

@media (max-width: 900px) {
  .detail-body {
    max-height: none;
  }
}
</style>
