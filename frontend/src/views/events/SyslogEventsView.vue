<template>
  <EventTypeView
    channel="syslog"
    eyebrow="Syslog"
    title="Syslog 事件中心"
    subtitle="按设备、对象、级别和事件类型查看 UDP Syslog 实时上报。"
    list-title="Syslog 实时流水"
  />
</template>

<script setup>
import EventTypeView from './EventTypeView.vue';
</script>
