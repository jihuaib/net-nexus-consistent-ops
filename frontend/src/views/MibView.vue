<template>
  <section class="view">
    <PageHeader
      eyebrow="MIB"
      title="厂商 MIB"
      subtitle="按厂商编译内置或上传 MIB，生成 MIB Tree，并为设备采集和后续 Trap 解析提供统一 OID 索引。"
    />

    <MibCompilerPanel />
  </section>
</template>

<script setup>
import MibCompilerPanel from '../components/MibCompilerPanel.vue';
import PageHeader from '../components/ui/PageHeader.vue';
</script>

<style scoped>
.view {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 8px;
  height: 100%;
  min-height: 0;
}
</style>
