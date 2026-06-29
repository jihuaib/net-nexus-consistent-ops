<template>
  <EventTypeView
    channel="grpc_telemetry"
    eyebrow="gRPC"
    title="gRPC 事件中心"
    subtitle="查看 gRPC/gNMI Telemetry 或兼容接入端点上报的指标事件。"
    list-title="gRPC Telemetry 实时流水"
  />
</template>

<script setup>
import EventTypeView from './EventTypeView.vue';
</script>
