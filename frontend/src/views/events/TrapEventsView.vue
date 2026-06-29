<template>
  <EventTypeView
    channel="snmp_trap"
    eyebrow="SNMP"
    title="SNMP 事件中心"
    subtitle="查看设备通过 SNMP Trap 上报的接口、路由和协议告警。"
    list-title="SNMP Trap 实时流水"
  />
</template>

<script setup>
import EventTypeView from './EventTypeView.vue';
</script>
