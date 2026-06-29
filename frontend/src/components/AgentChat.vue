<template>
  <section class="workspace">
    <header class="workspace-head">
      <div class="workspace-head__main">
        <h2>Agent 会话</h2>
        <p>Session: {{ sessionId }}</p>
      </div>
      <div class="session-actions">
        <select
          class="session-select"
          title="切换会话"
          :value="sessionId"
          :disabled="loading || !sessionRecords.length"
          @change="$emit('switch-session', $event.target.value)"
        >
          <option v-for="record in sessionRecords" :key="record.sessionId" :value="record.sessionId">
            {{ sessionOptionLabel(record) }}
          </option>
        </select>
        <button class="secondary" title="恢复当前会话记录" :disabled="loading" @click="$emit('restore-session', sessionId)">
          <History :size="15" />
          <span>恢复</span>
        </button>
        <button class="secondary" :disabled="loading" @click="$emit('reset-session')">
          <RotateCcw :size="15" />
          <span>新会话</span>
        </button>
      </div>
    </header>

    <section ref="chatWindowRef" class="chat-window" @scroll="updateScrollStickiness">
      <article
        v-for="message in messages"
        :key="message.id"
        class="message"
        :class="message.role"
      >
        <div class="avatar">{{ message.role === 'user' ? 'U' : 'A' }}</div>
        <div class="bubble">
          <span class="role">{{ message.role === 'user' ? '用户' : 'Agent' }}</span>
          <p>{{ message.content }}</p>
        </div>
      </article>
    </section>

    <section class="quick-actions">
      <button v-for="prompt in quickPrompts" :key="prompt" class="prompt" @click="$emit('quick', prompt)">
        {{ prompt }}
      </button>
    </section>

    <section class="composer">
      <textarea
        :value="input"
        rows="3"
        placeholder="输入运维问题，例如：leaf-01 为什么业务不通？"
        @input="$emit('update:input', $event.target.value)"
        @keydown.enter.exact.prevent="$emit('send')"
      ></textarea>
      <button @click="$emit('send')" :disabled="loading || !input.trim()">
        <Send :size="16" />
        <span>发送</span>
      </button>
    </section>
  </section>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue';
import { History, RotateCcw, Send } from '@lucide/vue';

const props = defineProps({
  loading: Boolean,
  sessionId: String,
  sessionRecords: {
    type: Array,
    default: () => [],
  },
  input: String,
  messages: {
    type: Array,
    default: () => [],
  },
  quickPrompts: {
    type: Array,
    default: () => [],
  },
});

defineEmits(['send', 'quick', 'switch-session', 'restore-session', 'reset-session', 'update:input']);

const chatWindowRef = ref(null);
const stickToBottom = ref(true);

function sessionOptionLabel(record) {
  const count = Number(record.messageCount || 0);
  const suffix = count ? ` · ${count} 条` : '';
  return `${record.title || record.sessionId}${suffix}`;
}

function updateScrollStickiness() {
  const element = chatWindowRef.value;
  if (!element) {
    return;
  }
  const distanceToBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
  stickToBottom.value = distanceToBottom < 96;
}

function scrollToBottomIfNeeded() {
  if (!stickToBottom.value) {
    return;
  }
  nextTick(() => {
    const element = chatWindowRef.value;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  });
}

watch(
  () => ({
    count: props.messages.length,
    signature: props.messages.map((message) => `${message.id}:${message.content?.length || 0}`).join('|'),
  }),
  (current, previous) => {
    if (previous && current.count > previous.count) {
      stickToBottom.value = true;
    }
    scrollToBottomIfNeeded();
  },
  { flush: 'post' }
);
</script>

<style scoped>
.workspace {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--nx-border);
  border-radius: 8px;
  background: var(--nx-surface-raised);
}

.workspace-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 46px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--nx-border);
}

.workspace-head__main {
  min-width: 0;
}

.workspace-head__main h2,
.workspace-head p {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-head p {
  margin-bottom: 0;
  color: var(--nx-text-dim);
  font-size: 11px;
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.session-select {
  width: 190px;
  min-width: 150px;
  height: 32px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 0 30px 0 10px;
  color: var(--nx-text);
  background: var(--nx-surface-2);
  font: inherit;
}

.chat-window {
  flex: 1 1 auto;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  display: grid;
  align-content: start;
  gap: 10px;
  min-height: 0;
  margin: 0 12px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 12px;
  background: var(--nx-bg);
}

.message {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  max-width: 880px;
}

.message.user {
  justify-self: end;
  grid-template-columns: minmax(0, 1fr) 34px;
}

.message.user .avatar {
  grid-column: 2;
  grid-row: 1;
  border-color: var(--nx-border);
  background: var(--nx-surface-2);
}

.message.user .bubble {
  grid-column: 1;
  grid-row: 1;
  background: var(--nx-accent-softer);
}

.avatar {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--nx-accent-border);
  border-radius: 7px;
  color: var(--nx-icon);
  background: var(--nx-accent-soft);
  font-size: 13px;
  font-weight: 800;
}

.bubble {
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px 12px;
  background: var(--nx-surface-2);
}

.bubble p {
  margin-bottom: 0;
  white-space: pre-line;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.role {
  display: block;
  margin-bottom: 5px;
  color: var(--nx-text-dim);
  font-size: 11px;
  font-weight: 700;
}

.quick-actions {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: nowrap;
  gap: 6px;
  overflow-x: auto;
  padding: 0 12px;
}

.prompt {
  flex: 0 0 auto;
  min-height: 32px;
  white-space: nowrap;
}

.composer {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 92px;
  align-items: end;
  gap: 8px;
  padding: 0 12px 12px;
}

.composer textarea {
  min-height: 68px;
  resize: none;
}

@media (max-width: 640px) {
  .workspace-head {
    align-items: stretch;
    flex-direction: column;
  }

  .session-actions {
    flex-wrap: wrap;
  }

  .session-select {
    flex: 1 1 100%;
    width: 100%;
  }

  .chat-window {
    min-height: 320px;
  }

  .quick-actions {
    flex-wrap: wrap;
    overflow-x: visible;
  }

  .composer {
    grid-template-columns: 1fr;
  }

  .message,
  .message.user {
    grid-template-columns: 30px minmax(0, 1fr);
    justify-self: stretch;
  }

  .message.user .avatar,
  .message.user .bubble {
    grid-column: auto;
    grid-row: auto;
  }
}
</style>
