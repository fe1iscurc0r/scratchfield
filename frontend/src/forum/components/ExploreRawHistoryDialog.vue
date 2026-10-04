<!-- 原始历史 Dialog（卷190-B4：从 ForumQuotaView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { Dialog } from 'primevue'

defineProps<{
  loading: boolean
  messages: Array<Record<string, any>>
}>()

const visible = defineModel<boolean>('visible', { required: true })
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="原始历史"
    :style="{ width: 'min(860px, 94vw)' }"
  >
    <div class="raw-history-list">
      <div v-if="loading" class="status-note">
        正在加载历史...
      </div>
      <template v-else-if="messages.length">
        <div
          v-for="(message, index) in messages"
          :key="index"
          class="raw-history-item"
        >
          <div class="raw-history-role">
            {{ String(message.role || 'unknown') }}
          </div>
          <pre>{{ typeof message.content === 'string' ? message.content : JSON.stringify(message, null, 2) }}</pre>
        </div>
      </template>
      <div v-else class="status-note">
        暂无历史。
      </div>
    </div>
  </Dialog>
</template>

<style scoped>
.raw-history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: min(620px, 70vh);
  overflow: auto;
}

.raw-history-item {
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.raw-history-role {
  margin-bottom: 6px;
  color: rgba(212, 175, 55, 0.86);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.raw-history-item pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: rgba(255, 255, 255, 0.68);
  font-size: 12px;
  line-height: 1.6;
}

.status-note {
  width: 100%;
  font-size: 11px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.52);
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 10px 12px;
}
</style>
