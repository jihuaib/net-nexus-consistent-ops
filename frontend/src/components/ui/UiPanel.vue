<template>
  <section class="ui-panel" :class="{ compact }">
    <header v-if="title || $slots.actions || eyebrow || subtitle" class="ui-panel-head">
      <div>
        <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
        <h2 v-if="title">{{ title }}</h2>
        <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="actions">
        <slot name="actions" />
      </div>
    </header>
    <slot />
  </section>
</template>

<script setup>
defineProps({
  title: String,
  subtitle: String,
  eyebrow: String,
  compact: Boolean,
});
</script>

<style scoped>
.ui-panel {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  background: var(--nx-surface-raised);
}

.ui-panel.compact {
  border-radius: 7px;
}

.ui-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  min-height: 46px;
  padding: 12px 12px 10px;
  border-bottom: 1px solid var(--nx-border);
}

.ui-panel-head h2 {
  margin: 0;
  font-size: 13px;
}

.eyebrow,
.subtitle {
  margin: 0;
  color: var(--nx-text-dim);
}

.eyebrow {
  margin-bottom: 4px;
  color: var(--nx-accent);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.subtitle {
  margin-top: 5px;
  font-size: 11px;
  line-height: 1.45;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ui-panel > :deep(:not(.ui-panel-head)) {
  padding: 12px;
}

@media (max-width: 640px) {
  .ui-panel-head {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
