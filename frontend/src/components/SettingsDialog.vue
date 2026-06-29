<template>
  <div class="settings-overlay">
    <section
      ref="panelRef"
      class="settings-panel"
      :class="{ 'is-dragging': dragging }"
      :style="surfaceStyle"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
    >
      <nav class="cats" aria-label="设置分类">
        <div class="cats__title" title="拖动移动弹窗" @pointerdown="startDrag">设置</div>
        <button
          v-for="cat in categories"
          :key="cat.id"
          class="cat"
          :class="{ active: cat.id === activeId }"
          type="button"
          @click="activeId = cat.id"
        >
          <span class="cat__icon">
            <component :is="cat.icon" :size="16" :stroke-width="1.9" />
          </span>
          <span>{{ cat.label }}</span>
        </button>
      </nav>

      <section class="content">
        <header class="content__head" title="拖动移动弹窗" @pointerdown="startDrag">
          <div>
            <h2 id="settings-title">{{ activeCategory.label }}</h2>
            <p>{{ activeCategory.description }}</p>
          </div>
          <div class="content__actions">
            <button class="icon-button" data-no-drag type="button" title="刷新" :disabled="loading" @click="$emit('refresh')">
              <RefreshCw :size="15" :stroke-width="1.9" />
            </button>
            <button class="icon-button" data-no-drag type="button" title="关闭" @click="$emit('close')">
              <X :size="16" :stroke-width="2" />
            </button>
          </div>
        </header>

        <div class="content__body">
          <LlmConfigPanel
            v-if="activeId === 'llm'"
            :config="llmConfig"
            :loading="loading"
            @save="$emit('save-llm-config', $event)"
          />
          <TopologyDiscoveryConfigPanel
            v-else-if="activeId === 'topology'"
            :config="topologyDiscoveryConfig"
            :loading="loading"
            @save="$emit('save-topology-config', $event)"
          />
        </div>
      </section>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { BrainCircuit, Network, RefreshCw, X } from '@lucide/vue';
import { useDraggableSurface } from '../composables/useDraggableSurface';
import LlmConfigPanel from './LlmConfigPanel.vue';
import TopologyDiscoveryConfigPanel from './TopologyDiscoveryConfigPanel.vue';

const props = defineProps({
  loading: Boolean,
  llmConfig: Object,
  topologyDiscoveryConfig: Object,
});

defineEmits(['close', 'refresh', 'save-llm-config', 'save-topology-config']);

const categories = [
  {
    id: 'llm',
    label: '模型接入',
    description: '配置 OpenAI-compatible 大模型接口和 JSON 输出能力。',
    icon: BrainCircuit,
  },
  {
    id: 'topology',
    label: '厂商采集',
    description: '配置厂商、管理网段、seed IP 和 SNMP community。',
    icon: Network,
  },
];

const activeId = ref('llm');
const activeCategory = computed(() => categories.find((cat) => cat.id === activeId.value) || categories[0]);
const panelRef = ref(null);
const { dragging, surfaceStyle, startDrag } = useDraggableSurface(panelRef);
</script>

<style scoped>
.settings-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
  background: rgba(37, 42, 50, 0.28);
}

.settings-panel {
  width: 780px;
  height: 560px;
  max-width: 94vw;
  max-height: 90vh;
  display: flex;
  overflow: hidden;
  will-change: transform;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  background: var(--nx-surface-raised);
  box-shadow: 0 24px 70px rgba(37, 42, 50, 0.24);
}

.settings-panel.is-dragging {
  user-select: none;
}

.cats {
  width: 190px;
  flex-shrink: 0;
  border-right: 1px solid var(--nx-border);
  padding: 14px 9px;
  background: var(--nx-rail-bg);
}

.cats__title {
  padding: 4px 10px 13px;
  color: var(--nx-text);
  font-weight: 700;
  cursor: move;
  touch-action: none;
  user-select: none;
}

.cat {
  width: 100%;
  min-height: 36px;
  justify-content: flex-start;
  gap: 9px;
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 0 10px;
  color: var(--nx-text);
  background: transparent;
  text-align: left;
}

.cat:hover {
  border-color: var(--nx-border);
  background: var(--nx-surface-2);
}

.cat.active {
  border-color: var(--nx-accent-border);
  color: var(--nx-accent);
  background: var(--nx-accent-soft);
}

.cat__icon {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  color: var(--nx-icon);
}

.content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.content__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 22px 16px;
  border-bottom: 1px solid var(--nx-border);
  cursor: move;
  touch-action: none;
  user-select: none;
}

.content__head h2 {
  margin: 0;
  font-size: 17px;
}

.content__head p {
  margin: 4px 0 0;
  color: var(--nx-text-dim);
  font-size: 12px;
}

.content__actions {
  display: flex;
  gap: 6px;
}

.icon-button {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  min-height: 30px;
  padding: 0;
  border-color: var(--nx-border);
  color: var(--nx-icon);
  background: var(--nx-surface-2);
}

.icon-button:hover {
  border-color: var(--nx-accent);
  background: var(--nx-accent-soft);
}

.content__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
  user-select: text;
}

.content__body :deep(*) {
  user-select: text;
}

.content__body :deep(button),
.content__body :deep(select),
.content__body :deep(input) {
  user-select: none;
}

@media (max-width: 680px) {
  .settings-panel {
    flex-direction: column;
  }

  .cats {
    width: 100%;
    display: flex;
    gap: 6px;
    overflow-x: auto;
    border-right: none;
    border-bottom: 1px solid var(--nx-border);
  }

  .cats__title {
    display: none;
  }

  .cat {
    width: auto;
    white-space: nowrap;
  }

}
</style>
