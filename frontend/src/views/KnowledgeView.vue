<template>
  <section class="view knowledge-view">
    <PageHeader eyebrow="RAG" title="知识库" subtitle="SOP、厂商手册、历史案例与检索验证。">
      <template #actions>
        <button class="secondary" :disabled="loading" title="刷新" @click="loadDocuments">
          <RefreshCw :size="15" />
          <span>刷新</span>
        </button>
        <button title="新建文档" @click="newDocument">
          <Plus :size="15" />
          <span>新建</span>
        </button>
        <button class="secondary" title="导入文件" @click="openImportDialog">
          <Upload :size="15" />
          <span>导入</span>
        </button>
      </template>
    </PageHeader>
    <input
      ref="fileInput"
      class="file-input"
      type="file"
      multiple
      accept=".md,.markdown,.txt,.json,text/markdown,text/plain,application/json"
      @change="handleFileInput"
    />

    <section class="knowledge-shell">
      <UiPanel class="library-panel" title="文档库" :subtitle="summaryText">
        <div class="panel-body library-body">
          <div class="library-filter">
            <Search :size="14" />
            <input v-model="documentFilter" placeholder="筛选标题、来源、标签" />
          </div>

          <button
            type="button"
            class="import-drop"
            :class="{ active: dragging }"
            @click="openImportDialog"
            @dragenter.prevent="dragging = true"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="handleDrop"
          >
            <Upload :size="16" />
            <span>Markdown / TXT / JSON</span>
          </button>

          <div class="document-list">
            <button
              v-for="document in filteredDocuments"
              :key="document.id"
              type="button"
              class="document-row"
              :class="{ active: document.id === selectedId }"
              @click="selectDocument(document)"
            >
              <span class="doc-icon">
                <Lock v-if="document.readonly" :size="15" />
                <FileText v-else :size="15" />
              </span>
              <span class="doc-main">
                <strong>{{ document.title }}</strong>
                <small>{{ document.source || 'operator' }}</small>
              </span>
              <span class="doc-meta">{{ document.readonly ? '内置' : `${document.content_length || 0} 字` }}</span>
            </button>
            <p v-if="!filteredDocuments.length" class="empty">无匹配文档。</p>
          </div>
        </div>
      </UiPanel>

      <UiPanel class="retrieval-panel" title="检索验证" :subtitle="searchSummaryText">
        <div class="panel-body retrieval-body">
          <form class="search-bar" @submit.prevent="runSearch">
            <Search :size="15" />
            <input v-model="query" placeholder="输入故障现象、设备、协议或报错原文" />
            <select v-model.number="searchLimit" title="返回数量">
              <option :value="3">3</option>
              <option :value="6">6</option>
              <option :value="10">10</option>
            </select>
            <button type="submit" :disabled="loading || !query.trim()">
              <Search :size="15" />
              <span>检索</span>
            </button>
          </form>

          <div class="result-list">
            <article v-for="item in results" :key="item.chunk_id" class="result-row">
              <header>
                <div>
                  <strong>{{ item.title }}</strong>
                  <small v-if="item.heading">{{ item.heading }}</small>
                </div>
                <span class="score">{{ formatScore(item.score) }}</span>
              </header>
              <p>{{ item.content }}</p>
              <footer>
                <span>{{ item.retrieval_backend || 'search' }}</span>
                <span>{{ item.source }}</span>
              </footer>
            </article>
            <p v-if="searched && !results.length" class="empty">没有命中知识片段。</p>
          </div>
        </div>
      </UiPanel>

      <UiPanel class="editor-panel" :title="editorTitle" :subtitle="editorSubtitle">
        <template #actions>
          <button type="button" :disabled="loading || form.readonly || !form.title || !form.content" @click="saveCurrent">
            <Save :size="15" />
            <span>保存</span>
          </button>
          <button class="secondary danger" type="button" :disabled="loading || !form.id || form.readonly" @click="removeCurrent">
            <Trash2 :size="15" />
            <span>删除</span>
          </button>
        </template>

        <form class="panel-body editor-body" @submit.prevent="saveCurrent">
          <div class="field-grid">
            <label>
              <span>标题</span>
              <input v-model="form.title" :disabled="form.readonly" placeholder="BGP 邻居中断排障 SOP" />
            </label>
            <label>
              <span>来源</span>
              <input v-model="form.source" :disabled="form.readonly" placeholder="vendor manual / runbook / ticket" />
            </label>
          </div>

          <label>
            <span>标签</span>
            <input v-model="tagText" :disabled="form.readonly" placeholder="BGP, route, H3C" />
          </label>

          <label class="content-field">
            <span>内容</span>
            <textarea v-model="form.content" :disabled="form.readonly" placeholder="粘贴排障步骤、告警解释或历史案例。" />
          </label>
        </form>
      </UiPanel>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { FileText, Lock, Plus, RefreshCw, Save, Search, Trash2, Upload } from '@lucide/vue';
import {
  deleteKnowledgeDocument,
  fetchKnowledgeDocuments,
  saveKnowledgeDocument,
  searchKnowledge,
} from '../api/consistentOpsApi';
import { normalizeErrorAlert, useAlerts } from '../composables/useAlerts';
import PageHeader from '../components/ui/PageHeader.vue';
import UiPanel from '../components/ui/UiPanel.vue';

const loading = ref(false);
const documents = ref([]);
const summary = ref(null);
const selectedId = ref('');
const fileInput = ref(null);
const dragging = ref(false);
const documentFilter = ref('');
const tagText = ref('');
const query = ref('BGP 邻居 Down 路由 FIB 业务不可达');
const searchLimit = ref(6);
const results = ref([]);
const searchSummary = ref(null);
const searched = ref(false);
const { pushAlert } = useAlerts();

const form = reactive({
  id: '',
  title: '',
  source: '',
  tags: [],
  content: '',
  readonly: false,
});

const filteredDocuments = computed(() => {
  const keyword = normalizeFilterText(documentFilter.value);
  if (!keyword) {
    return documents.value;
  }
  return documents.value.filter((document) => {
    const haystack = normalizeFilterText([
      document.title,
      document.source,
      ...(document.tags || []),
    ].join(' '));
    return haystack.includes(keyword);
  });
});

const summaryText = computed(() => {
  const total = summary.value?.total ?? documents.value.length;
  const builtin = summary.value?.builtin ?? 0;
  const custom = summary.value?.custom ?? 0;
  return `${total} 篇 · 内置 ${builtin} · 自定义 ${custom}`;
});

const searchSummaryText = computed(() => {
  if (!searched.value) {
    return '等待检索';
  }
  const backend = searchSummary.value?.backend || 'search';
  const returned = searchSummary.value?.returned ?? results.value.length;
  const chunks = searchSummary.value?.chunks ?? 0;
  return `${backend} · 返回 ${returned} / ${chunks}`;
});

const editorTitle = computed(() => (form.id ? '文档详情' : '新建文档'));
const editorSubtitle = computed(() => {
  if (!form.id) {
    return '自定义知识';
  }
  return form.readonly ? '只读内置文档' : '自定义文档';
});

onMounted(loadDocuments);

async function loadDocuments() {
  await withLoading(async () => {
    const data = await fetchKnowledgeDocuments();
    documents.value = data.items || [];
    summary.value = data.summary || null;
    if (!selectedId.value && documents.value.length) {
      selectDocument(documents.value[0]);
    }
    if (selectedId.value && !documents.value.some((document) => document.id === selectedId.value)) {
      selectDocument(documents.value[0] || {});
    }
  });
}

function selectDocument(document) {
  selectedId.value = document.id || '';
  form.id = document.id || '';
  form.title = document.title || '';
  form.source = document.source || '';
  form.tags = document.tags || [];
  form.content = document.content || '';
  form.readonly = Boolean(document.readonly);
  tagText.value = (form.tags || []).join(', ');
}

function newDocument() {
  selectedId.value = '';
  form.id = '';
  form.title = '';
  form.source = '';
  form.tags = [];
  form.content = '';
  form.readonly = false;
  tagText.value = '';
}

async function saveCurrent() {
  if (form.readonly || !form.title || !form.content) {
    return;
  }
  await withLoading(async () => {
    const response = await saveKnowledgeDocument({
      id: form.id || null,
      title: form.title,
      source: form.source,
      tags: parseTags(tagText.value),
      content: form.content,
    });
    pushAlert({ type: 'success', title: '知识已保存', message: response.document?.title || form.title });
    await loadDocuments();
    const saved = documents.value.find((document) => document.id === response.document?.id);
    if (saved) {
      selectDocument(saved);
    }
  });
}

async function removeCurrent() {
  if (!form.id || form.readonly) {
    return;
  }
  await withLoading(async () => {
    await deleteKnowledgeDocument(form.id);
    pushAlert({ type: 'success', title: '知识已删除', message: form.title });
    newDocument();
    await loadDocuments();
  });
}

function openImportDialog() {
  fileInput.value?.click();
}

async function handleFileInput(event) {
  const files = Array.from(event.target?.files || []);
  event.target.value = '';
  await importFiles(files);
}

async function handleDrop(event) {
  dragging.value = false;
  await importFiles(Array.from(event.dataTransfer?.files || []));
}

async function importFiles(files) {
  const supported = files.filter(isSupportedKnowledgeFile);
  if (!supported.length) {
    pushAlert({ type: 'warning', title: '未导入', message: '仅支持 Markdown、TXT、JSON 文件。' });
    return;
  }
  await withLoading(async () => {
    const documentsToImport = [];
    for (const file of supported) {
      const content = await file.text();
      documentsToImport.push(...documentsFromFile(file, content));
    }
    if (!documentsToImport.length) {
      pushAlert({ type: 'warning', title: '未导入', message: '文件中没有可保存的知识内容。' });
      return;
    }
    let savedCount = 0;
    for (const document of documentsToImport) {
      await saveKnowledgeDocument(document);
      savedCount += 1;
    }
    pushAlert({ type: 'success', title: '导入完成', message: `${savedCount} 篇知识文档已保存` });
    await loadDocuments();
    const latestCustom = [...documents.value].reverse().find((document) => !document.readonly);
    if (latestCustom) {
      selectDocument(latestCustom);
    }
  });
}

async function runSearch() {
  await withLoading(async () => {
    const response = await searchKnowledge({ query: query.value, limit: searchLimit.value });
    results.value = response.items || [];
    searchSummary.value = response.summary || null;
    searched.value = true;
  });
}

async function withLoading(task) {
  loading.value = true;
  try {
    await task();
  } catch (err) {
    pushAlert(normalizeErrorAlert(err));
  } finally {
    loading.value = false;
  }
}

function parseTags(value) {
  return String(value || '')
    .split(/[,\n;]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeFilterText(value) {
  return String(value || '').trim().toLowerCase();
}

function formatScore(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : '-';
}

function isSupportedKnowledgeFile(file) {
  return /\.(md|markdown|txt|json)$/i.test(file.name || '');
}

function documentsFromFile(file, content) {
  const extension = fileExtension(file.name);
  if (extension === 'json') {
    const imported = documentsFromJson(file, content);
    if (imported.length) {
      return imported;
    }
  }
  const title = firstMarkdownTitle(content) || fileBaseName(file.name);
  return [
    {
      title,
      source: file.name,
      tags: ['import', extension].filter(Boolean),
      content,
    },
  ];
}

function documentsFromJson(file, content) {
  try {
    const parsed = JSON.parse(content);
    const items = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.items) ? parsed.items : [parsed];
    return items
      .filter((item) => item && typeof item === 'object' && String(item.content || '').trim())
      .map((item, index) => ({
        title: String(item.title || item.name || `${fileBaseName(file.name)}-${index + 1}`).trim(),
        source: String(item.source || file.name).trim(),
        tags: Array.isArray(item.tags) ? item.tags : parseTags(item.tags || 'import,json'),
        content: String(item.content || '').trim(),
      }));
  } catch {
    return [];
  }
}

function firstMarkdownTitle(content) {
  const match = String(content || '').match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : '';
}

function fileBaseName(fileName) {
  return String(fileName || 'knowledge')
    .replace(/\.[^.]+$/, '')
    .replace(/[_-]+/g, ' ')
    .trim() || 'knowledge';
}

function fileExtension(fileName) {
  const match = String(fileName || '').match(/\.([^.]+)$/);
  return match ? match[1].toLowerCase() : '';
}
</script>

<style scoped>
.view {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 8px;
  height: 100%;
  min-height: 0;
}

.file-input {
  display: none;
}

.knowledge-shell {
  display: grid;
  grid-template-columns: minmax(250px, 0.72fr) minmax(420px, 1.35fr) minmax(340px, 1fr);
  gap: 8px;
  min-height: 0;
}

.library-panel,
.retrieval-panel,
.editor-panel {
  min-height: 0;
}

.panel-body {
  min-height: 0;
}

.library-body,
.retrieval-body,
.editor-body {
  display: grid;
  gap: 10px;
  height: 100%;
  min-height: 0;
}

.library-body {
  grid-template-rows: auto auto minmax(0, 1fr);
}

.retrieval-body {
  grid-template-rows: auto minmax(0, 1fr);
}

.editor-body {
  grid-template-rows: auto auto minmax(0, 1fr);
}

.library-filter,
.search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.library-filter {
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 0 8px;
  background: var(--nx-bg);
}

.library-filter svg {
  color: var(--nx-text-dim);
}

.library-filter input {
  border: 0;
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.import-drop {
  min-height: 40px;
  justify-content: flex-start;
  border-style: dashed;
  border-color: var(--nx-border);
  color: var(--nx-text-dim);
  background: var(--nx-bg);
}

.import-drop:hover,
.import-drop.active {
  border-color: var(--nx-accent-border);
  color: var(--nx-accent);
  background: var(--nx-accent-softer);
}

.search-bar input {
  flex: 1;
  min-width: 120px;
}

.search-bar select {
  width: 64px;
}

.document-list,
.result-list {
  display: grid;
  align-content: start;
  gap: 7px;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.document-row {
  width: 100%;
  min-height: 58px;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  border-color: var(--nx-border);
  padding: 8px;
  color: var(--nx-text);
  background: var(--nx-bg);
  text-align: left;
}

.document-row.active {
  border-color: var(--nx-accent-border);
  background: var(--nx-accent-soft);
}

.doc-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--nx-border-muted);
  border-radius: 6px;
  color: var(--nx-icon);
  background: var(--nx-surface);
}

.doc-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.doc-main strong,
.doc-main small,
.doc-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-main small,
.doc-meta,
.empty,
.result-row small,
.result-row footer {
  color: var(--nx-text-dim);
}

.doc-meta {
  max-width: 68px;
  font-size: 11px;
}

.result-row {
  display: grid;
  gap: 8px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.result-row header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.result-row header div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.result-row strong,
.result-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.score {
  min-width: 48px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--nx-accent-border-soft);
  border-radius: 6px;
  color: var(--nx-accent);
  background: var(--nx-accent-softer);
  font-family: var(--nx-font-mono);
  font-size: 12px;
  font-weight: 700;
}

.result-row p {
  max-height: 170px;
  overflow: auto;
  margin: 0;
  color: var(--nx-text);
  line-height: 1.55;
  white-space: pre-wrap;
}

.result-row footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  font-size: 11px;
}

.result-row footer span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.85fr);
  gap: 8px;
}

label {
  display: grid;
  gap: 5px;
  min-width: 0;
}

label span {
  color: var(--nx-text-dim);
  font-size: 12px;
  font-weight: 700;
}

.content-field {
  min-height: 0;
}

.content-field textarea {
  height: 100%;
  min-height: 260px;
  resize: none;
}

@media (max-width: 1260px) {
  .knowledge-shell {
    grid-template-columns: minmax(240px, 0.75fr) minmax(440px, 1.25fr);
  }

  .editor-panel {
    grid-column: 1 / -1;
    min-height: 420px;
  }
}

@media (max-width: 820px) {
  .knowledge-shell {
    grid-template-columns: 1fr;
  }

  .field-grid {
    grid-template-columns: 1fr;
  }

  .search-bar {
    align-items: stretch;
    flex-wrap: wrap;
  }

  .search-bar input {
    flex-basis: 100%;
  }
}
</style>
