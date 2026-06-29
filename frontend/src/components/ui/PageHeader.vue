<template>
  <header class="page-header">
    <div>
      <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
defineProps({
  title: {
    type: String,
    required: true,
  },
  subtitle: String,
  eyebrow: String,
});
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 54px;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--nx-surface-raised);
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

h1 {
  margin: 0;
  color: var(--nx-text);
  font-size: 17px;
}

.subtitle {
  max-width: 860px;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.55;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 720px) {
  .page-header {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
