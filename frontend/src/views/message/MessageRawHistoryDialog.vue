<!-- 原始探索记录 Dialog（卷190-B3：从 MessageView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import Dialog from 'primevue/dialog'

defineProps<{
  loading: boolean
  error: string
  timeline: Array<{
    id: string
    kind: 'assistant' | 'tool_call' | 'tool_result'
    title: string
    time: string
    text: string
  }>
  totalCount: number
}>()

const visible = defineModel<boolean>('visible', { required: true })
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="原始探索记录"
    :style="{ width: 'min(860px, 94vw)' }"
    :content-style="{ height: '82vh', overflow: 'hidden' }"
  >
    <div class="raw-history-panel">
      <div v-if="loading" class="travel-report-content">
        正在读取原始探索记录...
      </div>
      <div v-else-if="error" class="travel-report-content travel-report-missing">
        {{ error }}
      </div>
      <div v-else-if="!totalCount" class="travel-report-content travel-report-missing">
        暂无原始探索记录。
      </div>
      <div v-else class="raw-history-list">
        <div class="raw-history-toolbar">
          共 {{ timeline.length }} 条调度记录
        </div>
        <div v-if="!timeline.length" class="travel-report-content travel-report-missing">
          暂无可展示的 AI 回复或工具调度记录。
        </div>
        <div
          v-for="item in timeline"
          v-else
          :key="item.id"
          class="history-timeline-item"
          :class="item.kind"
        >
          <div class="history-timeline-head">
            <span class="history-timeline-title">{{ item.title }}</span>
            <span class="history-timeline-time">{{ item.time }}</span>
          </div>
          <pre class="history-timeline-body">{{ item.text }}</pre>
        </div>
      </div>
    </div>
  </Dialog>
</template>

<style scoped>
.travel-report-content {
  color: rgba(255, 255, 255, 0.74);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-report-missing {
  color: rgba(248, 113, 113, 0.9);
}

.raw-history-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
}

.raw-history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  flex: 1 1 auto;
  overflow: auto;
  padding-right: 4px;
}

.raw-history-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  position: sticky;
  top: 0;
  z-index: 1;
  padding-bottom: 2px;
  background: rgba(20, 20, 20, 0.92);
  color: rgba(255, 255, 255, 0.74);
  font-size: 12px;
  font-weight: 600;
}

.history-timeline-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
}

.history-timeline-item.assistant {
  border-color: rgba(96, 165, 250, 0.18);
  background: rgba(96, 165, 250, 0.06);
}

.history-timeline-item.tool_call {
  border-color: rgba(251, 191, 36, 0.18);
  background: rgba(251, 191, 36, 0.05);
}

.history-timeline-item.tool_result {
  border-color: rgba(66, 185, 131, 0.18);
  background: rgba(66, 185, 131, 0.05);
}

.history-timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.history-timeline-title {
  color: rgba(255, 255, 255, 0.86);
  font-size: 12px;
  font-weight: 700;
}

.history-timeline-time {
  color: rgba(255, 255, 255, 0.36);
  font-size: 11px;
}

.history-timeline-body {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  line-height: 1.6;
  max-height: 320px;
  overflow: auto;
}
</style>
