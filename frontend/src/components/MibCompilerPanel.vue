<template>
  <UiPanel class="mib-panel">
    <div class="mib-panel-body">
      <div class="mib-toolbar">
        <label class="file-picker">
          <input type="file" multiple accept=".mib,.txt,.my" @change="onFilesSelected" />
          <span>{{ selectedFilesText }}</span>
        </label>
        <button class="secondary" :disabled="loading || !selectedProfileId" @click="compileBuiltin">编译 MIB</button>
        <button :disabled="loading || !selectedProfileId || !selectedFiles.length" @click="compileWithUploads">
          编译上传 MIB
        </button>
        <div class="profile-select">
          <label for="mib-profile">厂商</label>
          <select id="mib-profile" v-model="selectedProfileId" :disabled="loading">
            <option v-for="profile in profiles" :key="profile.id" :value="profile.id">
              {{ vendorLabel(profile) }}
            </option>
          </select>
        </div>
      </div>

      <div v-if="summary" class="mib-summary">
        <div>
          <span>模块</span>
          <strong>{{ summary.modules?.length || 0 }}</strong>
        </div>
        <div>
          <span>对象</span>
          <strong>{{ summary.totalObjects || 0 }}</strong>
        </div>
        <div>
          <span>失败</span>
          <strong>{{ summary.failedFiles?.length || 0 }}</strong>
        </div>
        <div>
          <span>未解析</span>
          <strong>{{ summary.unresolvedObjects?.length || 0 }}</strong>
        </div>
      </div>

      <div class="mib-content">
        <section class="tree-panel">
          <div class="section-head">
            <h3>OID Tree</h3>
            <small>{{ compileResult?.compiledAt || '未编译' }}</small>
          </div>
          <ul v-if="tree.length" ref="treeRef" class="mib-tree">
            <MibTreeNode
              v-for="node in tree"
              :key="node.oid"
              :node="node"
              :expanded-oids="expandedOids"
              :highlighted-oid="highlightedOid"
            />
          </ul>
          <div v-else class="empty-state">暂无 MIB Tree</div>
        </section>

        <aside class="mib-side">
          <section class="side-section">
            <h3>OID 翻译</h3>
            <div class="translate-row">
              <input v-model="translateInput" placeholder=".1.3.6.1.2.1.1.5.0" :disabled="loading" />
              <button class="secondary" :disabled="loading || !translateInput.trim()" @click="translateOid">翻译</button>
            </div>
          </section>

          <section class="side-section">
            <h3>采集 OID 绑定</h3>
            <div v-if="bindingEntries.length" class="binding-list">
              <div v-for="[key, value] in bindingEntries" :key="key">
                <span>{{ key }}</span>
                <code>{{ value }}</code>
              </div>
            </div>
            <div v-else class="empty-state">无绑定</div>
          </section>

          <section v-if="summary?.failedFiles?.length || summary?.unresolvedObjects?.length" class="side-section">
            <h3>编译问题</h3>
            <div v-for="item in summary.failedFiles || []" :key="item.filePath" class="issue-row">
              <strong>{{ item.fileName }}</strong>
              <span>{{ item.msg }}</span>
            </div>
            <div v-for="item in summary.unresolvedObjects || []" :key="`${item.moduleName}-${item.objectName}`" class="issue-row">
              <strong>{{ item.moduleName }}::{{ item.objectName }}</strong>
              <span>缺少 {{ item.missingSymbol }}</span>
            </div>
          </section>
        </aside>
      </div>
    </div>
  </UiPanel>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { compileMibs, fetchMibProfiles, translateMibOid } from '../api/consistentOpsApi';
import { normalizeErrorAlert, useAlerts } from '../composables/useAlerts';
import MibTreeNode from './MibTreeNode.vue';
import UiPanel from './ui/UiPanel.vue';

const loading = ref(false);
const profiles = ref([]);
const selectedProfileId = ref('snmp_lldp');
const selectedFiles = ref([]);
const compileResult = ref(null);
const tree = ref([]);
const treeRef = ref(null);
const translateInput = ref('.1.3.6.1.2.1.1.5.0');
const translation = ref(null);
const expandedOids = ref(new Set());
const highlightedOid = ref('');
const { pushAlert } = useAlerts();

const selectedProfile = computed(() => profiles.value.find((profile) => profile.id === selectedProfileId.value));
const summary = computed(() => compileResult.value?.summary || null);
const bindingEntries = computed(() => Object.entries(compileResult.value?.oidBindings || selectedProfile.value?.oid_bindings || {}));
const selectedFilesText = computed(() => {
  if (!selectedFiles.value.length) {
    return '选择 MIB 文件';
  }
  return `${selectedFiles.value.length} 个文件`;
});

onMounted(async () => {
  await loadProfiles();
  if (selectedProfileId.value) {
    await compileBuiltin();
  }
});

watch(selectedProfileId, async (profileId, oldProfileId) => {
  if (!profileId || profileId === oldProfileId) {
    return;
  }
  selectedFiles.value = [];
  translation.value = null;
  clearTreeSelection();
  await compileBuiltin();
});

async function loadProfiles() {
  await runTask(async () => {
    const data = await fetchMibProfiles();
    profiles.value = data.items || [];
    if (!profiles.value.some((profile) => profile.id === selectedProfileId.value)) {
      selectedProfileId.value = profiles.value[0]?.id || '';
    }
  });
}

function onFilesSelected(event) {
  selectedFiles.value = Array.from(event.target.files || []);
}

async function compileBuiltin() {
  await compileSelected([]);
}

async function compileWithUploads() {
  const files = await Promise.all(
    selectedFiles.value.map(async (file) => ({
      file_name: file.name,
      content: await file.text(),
    }))
  );
  await compileSelected(files);
}

async function compileSelected(files) {
  await runTask(async () => {
    const data = await compileMibs({
      profile_id: selectedProfileId.value,
      files,
      include_tree: true,
    });
    compileResult.value = data;
    tree.value = data.tree || [];
    translation.value = null;
    clearTreeSelection();
  });
}

async function translateOid() {
  await runTask(async () => {
    const data = await translateMibOid({
      profileId: selectedProfileId.value,
      oid: translateInput.value.trim(),
    });
    translation.value = data.translation;
    focusTranslatedOid(data.translation);
  });
}

function vendorLabel(profile) {
  if (profile?.vendor === 'h3c') {
    return 'H3C 设备';
  }
  return '通用 SNMP 设备';
}

async function runTask(task) {
  loading.value = true;
  try {
    await task();
  } catch (err) {
    pushAlert(normalizeErrorAlert(err, 'MIB 操作失败'));
  } finally {
    loading.value = false;
  }
}

function focusTranslatedOid(result) {
  const targetOid = result?.object?.oid || (result?.exact ? result?.oid : '');
  if (!targetOid) {
    highlightedOid.value = '';
    pushAlert({
      type: 'warning',
      title: 'OID 未匹配',
      message: '当前 MIB Tree 中没有匹配到这个 OID。',
    });
    return;
  }

  expandedOids.value = new Set([targetOid, ...parentOids(targetOid)]);
  highlightedOid.value = targetOid;

  nextTick(() => {
    const selector = `[data-oid="${cssEscape(targetOid)}"]`;
    const element = treeRef.value?.querySelector(selector);
    element?.scrollIntoView?.({ block: 'center', inline: 'nearest', behavior: 'smooth' });
  });
}

function parentOids(oid) {
  const parts = String(oid || '').replace(/^\./, '').split('.').filter(Boolean);
  const parents = [];
  while (parts.length > 1) {
    parts.pop();
    parents.push(`.${parts.join('.')}`);
  }
  return parents;
}

function clearTreeSelection() {
  expandedOids.value = new Set();
  highlightedOid.value = '';
}

function cssEscape(value) {
  return String(value).replace(/["\\]/g, '\\$&');
}
</script>

<style scoped>
.mib-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.mib-panel-body {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 14px;
  flex: 1;
  min-height: 0;
}

.mib-toolbar,
.section-head,
.translate-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.profile-select {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 250px;
}

.profile-select label {
  flex: 0 0 auto;
  color: var(--nx-text-dim);
  font-size: 12px;
  font-weight: 700;
}

.profile-select select {
  height: 32px;
  min-height: 32px;
  min-width: 170px;
  line-height: 30px;
  padding-top: 0;
  padding-bottom: 0;
}

.mib-toolbar {
  justify-content: flex-start;
  flex-wrap: wrap;
}

.mib-toolbar button,
.file-picker span {
  height: 32px;
  min-height: 32px;
}

.file-picker input {
  display: none;
}

.file-picker span {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 0 14px;
  color: var(--nx-text);
  background: var(--nx-surface-2);
  font-weight: 600;
  cursor: pointer;
}

.file-picker span:hover {
  border-color: var(--nx-accent);
  color: var(--nx-accent);
}

.mib-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.mib-summary div {
  display: grid;
  gap: 4px;
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 10px;
  background: var(--nx-bg);
}

.mib-summary span,
.section-head small,
.empty-state,
.issue-row span {
  color: var(--nx-text-dim);
}

.mib-summary strong {
  color: var(--nx-text);
  font-size: 18px;
}

.mib-content {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 14px;
  min-height: 0;
}

.tree-panel,
.side-section {
  border: 1px solid var(--nx-border);
  border-radius: 7px;
  padding: 12px;
  background: var(--nx-bg);
}

.tree-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.mib-tree {
  flex: 1;
  min-height: 0;
  margin: 10px 0 0;
  padding: 0;
  overflow: auto;
}

.mib-side {
  display: grid;
  align-content: start;
  gap: 12px;
  min-height: 0;
  overflow: auto;
}

.translate-row input {
  min-width: 0;
}

.translate-row button {
  flex: 0 0 56px;
  width: 56px;
  padding: 0;
  white-space: nowrap;
}

code {
  overflow-wrap: anywhere;
  color: var(--nx-accent);
  font-size: 12px;
}

.binding-list,
.issue-row {
  display: grid;
  gap: 8px;
}

.binding-list div,
.issue-row {
  border-top: 1px solid var(--nx-border-soft);
  padding-top: 8px;
}

.binding-list span,
.issue-row strong {
  display: block;
  margin-bottom: 3px;
  color: var(--nx-text);
  font-size: 12px;
  font-weight: 700;
}

.empty-state {
  border: 1px dashed var(--nx-border);
  border-radius: 7px;
  padding: 14px;
  background: var(--nx-bg);
}

@media (max-width: 1100px) {
  .mib-content {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .panel-head,
  .mib-toolbar,
  .section-head,
  .translate-row {
    align-items: stretch;
    flex-direction: column;
  }

  .profile-select {
    align-items: stretch;
    flex-direction: column;
    min-width: 0;
  }

  .mib-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
