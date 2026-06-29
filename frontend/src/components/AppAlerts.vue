<template>
  <div class="alert-stack" aria-live="polite">
    <article v-for="alert in alerts" :key="alert.id" class="app-alert" :class="alert.type">
      <span class="alert-icon">
        <CheckCircle v-if="alert.type === 'success'" :size="18" :stroke-width="1.9" />
        <Info v-else-if="alert.type === 'info'" :size="18" :stroke-width="1.9" />
        <TriangleAlert v-else-if="alert.type === 'warning'" :size="18" :stroke-width="1.9" />
        <CircleX v-else :size="18" :stroke-width="1.9" />
      </span>
      <div class="alert-copy">
        <strong>{{ alert.title }}</strong>
        <span>{{ alert.message }}</span>
        <details v-if="alert.detail">
          <summary>详细信息</summary>
          <p>{{ alert.detail }}</p>
        </details>
      </div>
      <button class="alert-close" type="button" title="关闭" @click="dismissAlert(alert.id)">
        <X :size="15" :stroke-width="2" />
      </button>
    </article>
  </div>
</template>

<script setup>
import { CheckCircle, CircleX, Info, TriangleAlert, X } from '@lucide/vue';
import { useAlerts } from '../composables/useAlerts';

const { alerts, dismissAlert } = useAlerts();
</script>

<style scoped>
.alert-stack {
  position: fixed;
  z-index: 260;
  top: 64px;
  left: 50%;
  display: grid;
  gap: 8px;
  width: min(560px, calc(100vw - 32px));
  max-height: calc(100vh - 88px);
  transform: translateX(-50%);
  pointer-events: none;
}

.app-alert {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: flex-start;
  min-height: 54px;
  max-height: min(360px, calc(100vh - 72px));
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  padding: 12px 10px 12px 12px;
  color: var(--nx-text);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 18px 44px rgba(37, 42, 50, 0.18);
  overflow: hidden;
  pointer-events: auto;
}

.app-alert.success {
  border-color: rgba(22, 130, 91, 0.38);
}

.app-alert.info {
  border-color: var(--nx-accent-border-soft);
}

.app-alert.warning {
  border-color: rgba(183, 121, 31, 0.42);
}

.app-alert.error {
  border-color: var(--nx-danger-border);
}

.alert-icon {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  color: var(--nx-accent);
}

.app-alert.success .alert-icon {
  color: var(--nx-success);
}

.app-alert.warning .alert-icon {
  color: var(--nx-warning);
}

.app-alert.error .alert-icon {
  color: var(--nx-danger);
}

.alert-copy {
  min-width: 0;
  display: grid;
  gap: 4px;
  line-height: 1.4;
  overflow: hidden;
}

.alert-copy strong {
  min-width: 0;
  font-size: 13px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.alert-copy span,
.alert-copy p,
.alert-copy summary {
  color: var(--nx-text-dim);
  font-size: 12px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.alert-copy details {
  margin-top: 2px;
  min-width: 0;
  overflow: hidden;
}

.alert-copy summary {
  max-width: 100%;
  cursor: pointer;
}

.alert-copy p {
  max-height: 180px;
  margin: 6px 0 0;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.alert-close {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  min-height: 26px;
  border-color: transparent;
  padding: 0;
  color: var(--nx-icon);
  background: transparent;
}

.alert-close:hover {
  border-color: var(--nx-border);
  background: var(--nx-surface-2);
}

@media (max-width: 560px) {
  .alert-stack {
    top: 58px;
    width: calc(100vw - 20px);
  }
}
</style>
