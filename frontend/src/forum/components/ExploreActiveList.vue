<!-- 进行中探索列表（卷190-B4：从 ForumQuotaView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { Button } from 'primevue'

defineProps<{
  sessions: any[]
  currentSessionId: string | null | undefined
}>()

const emit = defineEmits<{
  view: [session: any]
  stop: [sessionId: string]
}>()
</script>

<template>
  <div class="goal-block">
    <div class="stats-label">进行中的探索</div>
    <div class="active-session-list">
      <button
        v-for="session in sessions"
        :key="session.sessionId"
        class="active-session-card"
        :class="{ current: currentSessionId === session.sessionId }"
        @click="emit('view', session)"
      >
        <div class="active-session-head">
          <div class="active-session-title">
            {{ session.agentName || '默认干员' }}
          </div>
          <Button
            size="small"
            text
            severity="danger"
            label="取消"
            @click.stop="emit('stop', session.sessionId)"
          />
        </div>
        <div class="active-session-desc">
          {{ session.goalPrompt || '自由探索最新热点' }}
        </div>
        <div class="active-session-meta">
          {{ session.discoveries.length }} 个发现 · {{ session.uniqueSources || 0 }} 个来源
        </div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.goal-block {
  width: 100%;
}

.stats-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

.active-session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.active-session-card {
  width: 100%;
  padding: 12px;
  text-align: left;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.active-session-card.current {
  border-color: rgba(212, 175, 55, 0.35);
  background: rgba(212, 175, 55, 0.08);
}

.active-session-title {
  color: rgba(255, 255, 255, 0.88);
  font-size: 12px;
  font-weight: 700;
}

.active-session-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.active-session-desc {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.48);
  font-size: 11px;
  line-height: 1.5;
}

.active-session-meta {
  margin-top: 8px;
  color: rgba(255, 255, 255, 0.34);
  font-size: 10px;
}
</style>
