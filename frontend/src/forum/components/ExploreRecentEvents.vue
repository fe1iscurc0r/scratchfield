<!-- 最近进展事件列表（卷190-B4：从 ForumQuotaView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
defineProps<{
  events: Array<any>
}>()
</script>

<template>
  <div class="report-block">
    <div class="stats-label">最近进展</div>
    <div class="events-list">
      <div
        v-for="(event, index) in events"
        :key="`${event.timestamp}-${event.type}-${index}`"
        class="event-card"
        :class="event.level || 'info'"
      >
        <div class="event-head">
          <span>{{ event.type }}</span>
          <span>{{ event.timestamp ? event.timestamp.slice(11, 19) : '--:--:--' }}</span>
        </div>
        <div class="event-body">{{ event.message }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.report-block {
  width: 100%;
}

.stats-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.event-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  padding: 10px 12px;
}

.event-card.warn {
  border-color: rgba(251, 191, 36, 0.18);
  background: rgba(251, 191, 36, 0.06);
}

.event-card.error {
  border-color: rgba(248, 113, 113, 0.18);
  background: rgba(248, 113, 113, 0.06);
}

.event-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: rgba(255, 255, 255, 0.34);
  font-size: 10px;
}

.event-body {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.78);
  font-size: 11px;
  line-height: 1.6;
}
</style>
