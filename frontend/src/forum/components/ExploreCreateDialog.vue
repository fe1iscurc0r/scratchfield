<!-- 新建探索 Dialog（卷190-B4：从 ForumQuotaView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { Button, Dialog, InputNumber, Select, Textarea, ToggleSwitch } from 'primevue'

defineProps<{
  createAgentOptions: any[]
  busyAgentOptions: any[]
  openclawAgents: any[]
  loading: boolean
  canStart: boolean
}>()
const emit = defineEmits<{
  start: []
  refresh: []
}>()
const visible = defineModel<boolean>('visible', { required: true })
const goalPrompt = defineModel<string>('goalPrompt', { required: true })
const selectedAgentId = defineModel<string>('selectedAgentId', { required: true })
const timeLimitMinutes = defineModel<number>('timeLimitMinutes', { required: true })
const creditLimit = defineModel<number>('creditLimit', { required: true })
const browserVisible = defineModel<boolean>('browserVisible', { required: true })
const browserKeepOpen = defineModel<boolean>('browserKeepOpen', { required: true })
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="新建探索"
    :style="{ width: 'min(760px, 92vw)' }"
  >
    <div class="create-panel">
      <div class="goal-block">
        <div class="label-row">
          <div class="stats-label">执行干员</div>
          <button
            type="button"
            class="label-refresh-btn"
            title="刷新干员列表"
            aria-label="刷新干员列表"
            @click="emit('refresh')"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5" />
            </svg>
          </button>
        </div>
        <Select
          v-model="selectedAgentId"
          :options="createAgentOptions"
          option-label="name"
          option-value="id"
          class="goal-input"
          placeholder="选择一个通讯录中的干员"
          :disabled="!createAgentOptions.length"
          append-to="body"
        />
        <div v-if="!openclawAgents.length" class="status-note">
          先在干员通讯录中创建一个 OpenClaw 干员，探索会直接使用该干员的人格模板与实例记忆。
        </div>
        <div v-else-if="!createAgentOptions.length" class="status-note">
          当前没有空闲干员可用于新建探索，请等待已有探索完成后再试。
        </div>
        <div v-else-if="busyAgentOptions.length" class="status-note">
          已在探索中的干员：{{ busyAgentOptions.map(agent => agent.name).join('、') }}
        </div>
      </div>

      <div class="goal-block">
        <div class="stats-label">探索方向</div>
        <Textarea
          v-model="goalPrompt"
          rows="4"
          class="goal-input resize-none"
          placeholder="例如：今天海外 AI 圈的最新热点、前沿产品、开发者社区里最值得跟进的讨论"
        />
      </div>

      <div class="goal-block">
        <div class="stats-label">探索配额</div>
        <div class="limits-grid">
          <div class="limit-card">
            <div class="meta-label">时间上限</div>
            <InputNumber
              v-model="timeLimitMinutes"
              :min="5"
              :max="720"
              show-buttons
              suffix=" 分钟"
              class="limit-input"
            />
          </div>
          <div class="limit-card">
            <div class="meta-label">积分上限</div>
            <InputNumber
              v-model="creditLimit"
              :min="100"
              :max="10000"
              show-buttons
              suffix=" 积分"
              class="limit-input"
            />
          </div>
        </div>
        <div class="status-note">
          当前论坛入口会严格按你上面填写的时间和积分上限启动探索。
        </div>
      </div>

      <div class="goal-block">
        <div class="stats-label">浏览器策略</div>
        <div class="browser-policy-grid">
          <div class="policy-card">
            <div>
              <div class="policy-title">浏览器可见</div>
              <div class="policy-desc">打开后探索会尽量用可见窗口执行后续浏览器动作。</div>
            </div>
            <ToggleSwitch v-model="browserVisible" :disabled="!selectedAgentId" class="policy-switch" />
          </div>
          <div class="policy-card">
            <div>
              <div class="policy-title">页面保持打开</div>
              <div class="policy-desc">关闭时空闲 300 秒自动关闭；打开后不自动回收标签页。</div>
            </div>
            <ToggleSwitch v-model="browserKeepOpen" :disabled="!selectedAgentId" class="policy-switch" />
          </div>
        </div>
      </div>
    </div>
    <template #footer>
      <Button label="取消" text @click="visible = false" />
      <Button
        label="开始探索"
        :loading="loading"
        :disabled="!canStart"
        @click="emit('start')"
      />
    </template>
  </Dialog>
</template>

<style scoped>
.create-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.create-panel > .goal-block {
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 10px;
  background: transparent;
}

.stats-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

.label-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
}

.label-row .stats-label {
  margin-bottom: 0;
}

.label-refresh-btn {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.58);
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.label-refresh-btn:hover {
  border-color: rgba(212, 175, 55, 0.32);
  background: rgba(212, 175, 55, 0.08);
  color: rgba(212, 175, 55, 0.86);
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

.limits-grid,
.browser-policy-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.limit-card,
.policy-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
}

.limit-card {
  padding: 12px;
}

.limit-input {
  width: 100%;
}

.policy-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
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

.meta-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}

.goal-input :deep(textarea) {
  width: 100%;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.82);
}

.goal-input {
  width: 100%;
}

.goal-input :deep(.p-textarea),
.goal-input :deep(.p-inputtext),
.goal-input :deep(.p-select) {
  width: 100%;
}

@media (max-width: 1100px) {
  .limits-grid,
  .browser-policy-grid {
    grid-template-columns: 1fr;
  }
}
</style>
