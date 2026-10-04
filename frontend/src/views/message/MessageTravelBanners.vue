<!-- 探索横幅（卷190-B3：从 MessageView.vue 纯搬移；原文件 normal/expanded 双份模板逐字相同，收敛为单组件双挂载） -->
<script setup lang="ts">
import Markdown from '@/components/Markdown.vue'

defineProps<{
  activeAgentTravel: any
  completedAgentTravel: any
  activeAgentTravelMeta: string
  loadingCompletedTravelReport: boolean
  completedTravelReport: any
}>()

const emit = defineEmits<{
  openRawHistory: []
}>()
</script>

<template>
  <div v-if="activeAgentTravel" class="travel-status-banner">
    <div class="travel-status-title">
      <span class="travel-status-spinner" />
      探索中
    </div>
    <div class="travel-status-summary">
      {{ activeAgentTravel.goalPrompt || '正在执行后台探索任务' }}
    </div>
    <div class="travel-status-meta">
      {{ activeAgentTravelMeta }}
    </div>
    <button class="travel-action-btn" @click="emit('openRawHistory')">
      查看原始探索记录
    </button>
  </div>
  <div v-else-if="completedAgentTravel" class="travel-report-banner">
    <div class="travel-report-title">探索完成成果</div>
    <div class="travel-report-meta">
      {{ completedAgentTravel.goalPrompt || '最近一次探索已完成' }}
    </div>
    <div v-if="loadingCompletedTravelReport" class="travel-report-content">
      正在读取探索成果文件...
    </div>
    <template v-else-if="completedTravelReport?.exists">
      <div class="travel-report-file">
        {{ completedTravelReport.title || '探索成果文件' }}
        <span v-if="completedTravelReport.path"> · {{ completedTravelReport.path.split('/').pop() }}</span>
      </div>
      <div class="travel-report-content travel-report-markdown">
        <Markdown :source="completedTravelReport.content || ''" />
      </div>
    </template>
    <div v-else class="travel-report-content travel-report-missing">
      {{ completedTravelReport?.missingReason === 'missing' ? '找不到探索成果文件。' : '尚未生成探索成果文件。' }}
    </div>
    <button class="travel-action-btn" @click="emit('openRawHistory')">
      查看原始探索记录
    </button>
  </div>
</template>

<style scoped>
.travel-status-banner {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: min(760px, 100%);
  max-width: 100%;
  align-self: flex-start;
  padding: 10px 12px;
  border: 1px solid rgba(66, 185, 131, 0.22);
  border-radius: 12px;
  background: rgba(66, 185, 131, 0.08);
}

.travel-status-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(224, 255, 238, 0.92);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.travel-status-spinner {
  width: 10px;
  height: 10px;
  border: 2px solid rgba(224, 255, 238, 0.26);
  border-top-color: rgba(224, 255, 238, 0.92);
  border-radius: 50%;
  animation: travel-spin 0.9s linear infinite;
}

@keyframes travel-spin {
  to { transform: rotate(360deg); }
}

.travel-status-summary {
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-status-meta {
  color: rgba(224, 255, 238, 0.55);
  font-size: 11px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-action-btn {
  align-self: flex-start;
  padding: 4px 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.66);
  font-size: 11px;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.travel-action-btn:hover {
  border-color: rgba(96, 165, 250, 0.28);
  background: rgba(96, 165, 250, 0.1);
  color: rgba(226, 238, 255, 0.92);
}

.travel-report-banner {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: min(760px, 100%);
  max-width: 100%;
  align-self: flex-start;
  padding: 10px 12px;
  border: 1px solid rgba(96, 165, 250, 0.22);
  border-radius: 12px;
  background: rgba(96, 165, 250, 0.08);
}

.travel-report-title {
  color: rgba(226, 238, 255, 0.92);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.travel-report-meta {
  color: rgba(226, 238, 255, 0.56);
  font-size: 11px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-report-file {
  color: rgba(255, 255, 255, 0.8);
  font-size: 11px;
  font-weight: 600;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-report-content {
  color: rgba(255, 255, 255, 0.74);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-report-markdown {
  white-space: normal;
}

.travel-report-markdown :deep(h1),
.travel-report-markdown :deep(h2),
.travel-report-markdown :deep(h3),
.travel-report-markdown :deep(h4) {
  color: rgba(255, 255, 255, 0.9);
  margin: 0.9em 0 0.45em;
}

.travel-report-markdown :deep(p),
.travel-report-markdown :deep(li) {
  color: rgba(255, 255, 255, 0.74);
  line-height: 1.7;
}

.travel-report-markdown :deep(strong) {
  color: rgba(255, 255, 255, 0.9);
}

.travel-report-missing {
  color: rgba(248, 113, 113, 0.9);
}
</style>
