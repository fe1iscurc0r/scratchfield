<!-- 当前探索状态面板（卷190-B4：从 ForumQuotaView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { Button, ToggleSwitch } from 'primevue'

defineProps<{
  session: any
  statusTone: string
  statusLabel: string
  phaseLabel: string
  remainingMinutes: number
  remainingCredits: number
  timeProgress: number
  creditProgress: number
  lastUpdatedLabel: string
  rawHistoryLoading: boolean
}>()

const emit = defineEmits<{
  stop: []
  rawHistory: []
  browserSettings: [params: { browserVisible?: boolean, browserKeepOpen?: boolean }]
}>()
</script>

<template>
  <div class="status-panel" :class="statusTone">
    <div class="status-panel-top">
      <div class="status-panel-title">
        {{ statusLabel }}
      </div>
      <div class="status-panel-time">
        最近刷新 {{ lastUpdatedLabel }}
      </div>
    </div>
    <div class="phase-chip">
      当前阶段：{{ phaseLabel }}
      <span v-if="session.phaseStartedAt"> · 阶段开始 {{ session.phaseStartedAt.slice(11, 19) }}</span>
      <span v-if="session.lastCheckpointAt"> · 最近检查点 {{ session.lastCheckpointAt.slice(11, 19) }}</span>
    </div>
    <div class="status-metrics">
      <div class="metric">
        <span class="meta-label">剩余时间</span>
        <span class="meta-val">{{ Math.max(0, Math.round(remainingMinutes)) }} 分钟</span>
      </div>
      <div class="metric">
        <span class="meta-label">剩余积分</span>
        <span class="meta-val">{{ remainingCredits }}</span>
      </div>
      <div class="metric">
        <span class="meta-label">已用时间</span>
        <span class="meta-val">{{ Math.round(session.elapsedMinutes) }} / {{ session.timeLimitMinutes }}</span>
      </div>
      <div class="metric">
        <span class="meta-label">已用积分</span>
        <span class="meta-val">{{ session.creditsUsed }} / {{ session.creditLimit }}</span>
      </div>
    </div>
    <div class="progress-bars">
      <div class="progress-row">
        <div class="progress-label">时间进度</div>
        <div class="progress-track"><div class="progress-fill" :style="{ width: `${timeProgress}%` }" /></div>
      </div>
      <div class="progress-row">
        <div class="progress-label">积分进度</div>
        <div class="progress-track"><div class="progress-fill accent" :style="{ width: `${creditProgress}%` }" /></div>
      </div>
    </div>
    <div v-if="session.status === 'pending' || session.status === 'running' || session.status === 'interrupted'" class="status-actions">
      <Button
        label="终止当前探索"
        severity="danger"
        outlined
        @click="emit('stop')"
      />
      <Button
        label="查看原始历史"
        outlined
        :loading="rawHistoryLoading"
        @click="emit('rawHistory')"
      />
    </div>
    <div v-if="session.status === 'pending' || session.status === 'running' || session.status === 'interrupted'" class="browser-live-settings">
      <div class="policy-card">
        <div>
          <div class="policy-title">浏览器可见</div>
          <div class="policy-desc">运行中的探索会尽量切换到可见窗口继续浏览。</div>
        </div>
        <ToggleSwitch
          :model-value="Boolean(session.browserVisible)"
          class="policy-switch"
          @update:model-value="emit('browserSettings', { browserVisible: $event })"
        />
      </div>
      <div class="policy-card">
        <div>
          <div class="policy-title">页面保持打开</div>
          <div class="policy-desc">关闭时空闲后自动回收；打开后保留浏览标签页。</div>
        </div>
        <ToggleSwitch
          :model-value="Boolean(session.browserKeepOpen)"
          class="policy-switch"
          @update:model-value="emit('browserSettings', { browserKeepOpen: $event })"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.status-panel {
  width: 100%;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
}

.status-panel.active {
  border-color: rgba(52, 211, 153, 0.24);
  background: rgba(52, 211, 153, 0.06);
}

.status-panel.ok {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.06);
}

.status-panel.warn {
  border-color: rgba(251, 191, 36, 0.24);
  background: rgba(251, 191, 36, 0.06);
}

.status-panel.danger {
  border-color: rgba(248, 113, 113, 0.24);
  background: rgba(248, 113, 113, 0.06);
}

.status-panel-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.status-panel-title {
  color: rgba(255, 255, 255, 0.9);
  font-size: 13px;
  font-weight: 700;
}

.status-panel-time {
  color: rgba(255, 255, 255, 0.38);
  font-size: 10px;
}

.phase-chip {
  margin-top: 10px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 11px;
  line-height: 1.6;
}

.status-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}

.meta-val {
  font-size: 14px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.75);
  font-variant-numeric: tabular-nums;
}

.progress-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.status-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-top: 12px;
}

.browser-live-settings {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.policy-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
}

.policy-switch {
  flex: 0 0 auto;
  min-width: 52px;
}

.policy-switch :deep(.p-toggleswitch-slider) {
  min-width: 52px;
}

.policy-title {
  color: rgba(255, 255, 255, 0.84);
  font-size: 12px;
  font-weight: 600;
}

.policy-desc {
  margin-top: 4px;
  color: rgba(255, 255, 255, 0.4);
  font-size: 11px;
  line-height: 1.5;
}

.progress-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.progress-label {
  color: rgba(255, 255, 255, 0.45);
  font-size: 10px;
}

.progress-track {
  position: relative;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.08);
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: rgba(96, 165, 250, 0.9);
}

.progress-fill.accent {
  background: rgba(212, 175, 55, 0.9);
}

@media (max-width: 1100px) {
  .browser-live-settings,
  .status-metrics {
    grid-template-columns: 1fr;
  }

  .progress-row {
    grid-template-columns: 1fr;
  }
}
</style>
