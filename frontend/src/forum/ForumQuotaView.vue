<!-- 网络探索页壳（卷190-B4：逻辑拆至 forum/composables/*，视图拆至 forum/components/*；纯搬移，行为零变化） -->
<script setup lang="ts">
import ScrollPanel from 'primevue/scrollpanel'
import { onMounted, ref } from 'vue'
import TravelDiscoveryItem from '@/travel/components/TravelDiscoveryItem.vue'
import TravelHistoryList from '@/travel/components/TravelHistoryList.vue'
import { useTravel } from '@/travel/composables/useTravel'
import { loadAgentContacts } from '@/utils/session'
import ExploreActiveList from './components/ExploreActiveList.vue'
import ExploreCreateDialog from './components/ExploreCreateDialog.vue'
import ExploreHelpDialog from './components/ExploreHelpDialog.vue'
import ExploreRawHistoryDialog from './components/ExploreRawHistoryDialog.vue'
import ExploreRecentEvents from './components/ExploreRecentEvents.vue'
import ExploreStatsGrid from './components/ExploreStatsGrid.vue'
import ExploreStatusPanel from './components/ExploreStatusPanel.vue'
import ForumSidebarLeft from './components/ForumSidebarLeft.vue'
import ForumSidebarRight from './components/ForumSidebarRight.vue'
import QuotaGauge from './components/QuotaGauge.vue'
import { useCreateExploreForm } from './composables/useCreateExploreForm'
import { useExploreSessionOps } from './composables/useExploreSessionOps'
import { useQuotaDashboard } from './composables/useQuotaDashboard'
import { useForumProfile } from './useAgentProfile'

const { profile, profileError, load, reload } = useForumProfile()
const {
  travelSession,
  activeSessions,
  activeSessionByAgentId,
  historyList,
  loading,
  timeProgress,
  creditProgress,
  lastUpdatedLabel,
  startTravel,
  stopTravel,
  updateTravelBrowserSettings,
  viewSession,
  refreshSessions,
} = useTravel()

// ── 领域组装（依赖方向：dashboard ← form（quotaRemaining 由 dashboard 提供），无环） ──
const dashboard = useQuotaDashboard({ profile, travelSession, activeSessions, historyList, reload })
const form = useCreateExploreForm({
  activeSessions,
  activeSessionByAgentId,
  quotaRemaining: dashboard.quotaRemaining,
  effectiveDailyBudget: dashboard.effectiveDailyBudget,
  refreshSessions,
  startTravel,
})
const ops = useExploreSessionOps({ currentSession: dashboard.currentSession, stopTravel, updateTravelBrowserSettings })

const {
  exploring,
  currentSession,
  realCredits,
  effectiveDailyBudget,
  effectiveUsedToday,
  currentFindings,
  currentSources,
  currentSocial,
  phaseLabel,
  remainingMinutes,
  remainingCredits,
  recentEvents,
  statusTone,
  statusLabel,
  sessionNotice,
  quotaRemaining,
  quotaPercent,
} = dashboard
const {
  createDialogVisible,
  goalPrompt,
  selectedAgentId,
  timeLimitMinutes,
  creditLimit,
  createBrowserVisible,
  createBrowserKeepOpen,
  openclawAgents,
  busyAgentOptions,
  createAgentOptions,
  canStartForSelectedAgent,
  refreshAgentOptions,
  toggleExplore,
} = form
const {
  rawHistoryVisible,
  rawHistoryLoading,
  rawHistoryMessages,
  stopCurrentSession,
  stopListedSession,
  updateCurrentBrowserSettings,
  openRawHistory,
} = ops

const helpVisible = ref(false)

onMounted(() => {
  void load()
  void loadAgentContacts()
})
</script>

<template>
  <template v-if="true">
    <ForumSidebarLeft
      :total-posts="0"
      :total-comments="0"
      back-label="返回网络"
      back-to="/forum"
      show-home-button
      home-label="返回首页"
      home-to="/"
      hide-filters
    />

    <div class="main-col flex-1 min-w-0 min-h-0 self-stretch">
      <ScrollPanel
        class="size-full"
        :pt="{ barY: { class: 'w-2! rounded! bg-#373737! transition!' } }"
      >
        <div class="page">
          <div class="title-row">
            <h2 class="title">网络探索</h2>
            <button class="help-btn" type="button" @click="helpVisible = true">
              ?
            </button>
          </div>

          <!-- ── 剩余流量 ── -->
          <QuotaGauge
            :quota-remaining="quotaRemaining"
            :quota-percent="quotaPercent"
            :effective-daily-budget="effectiveDailyBudget"
            :effective-used-today="effectiveUsedToday"
            :real-credits="realCredits"
          />

          <div v-if="profileError" class="status-note warn">
            论坛资料暂不可用：{{ profileError }}。本地探索仍可继续。
          </div>

          <!-- ── 本次探索成果 ── -->
          <ExploreStatsGrid
            :findings="currentFindings"
            :sources="currentSources"
            :social="currentSocial"
          />
          <div class="create-toolbar">
            <button class="create-trigger-btn" type="button" @click="createDialogVisible = true">
              <span>新建探索</span>
              <span class="create-trigger-icon">›</span>
            </button>
          </div>

          <ExploreActiveList
            v-if="activeSessions.length"
            :sessions="activeSessions"
            :current-session-id="currentSession?.sessionId"
            @view="viewSession"
            @stop="stopListedSession"
          />
          <div v-if="exploring" class="explore-hint">
            OpenClaw 正在浏览网页、搜索热点并整理发现。当前论坛入口已经支持多干员并行探索，切换干员后可继续新建任务。
          </div>

          <div v-if="sessionNotice" class="status-note" :class="sessionNotice.tone">
            {{ sessionNotice.text }}
          </div>

          <ExploreStatusPanel
            v-if="currentSession"
            :session="currentSession"
            :status-tone="statusTone"
            :status-label="statusLabel"
            :phase-label="phaseLabel"
            :remaining-minutes="remainingMinutes"
            :remaining-credits="remainingCredits"
            :time-progress="timeProgress"
            :credit-progress="creditProgress"
            :last-updated-label="lastUpdatedLabel"
            :raw-history-loading="rawHistoryLoading"
            @stop="stopCurrentSession"
            @raw-history="openRawHistory"
            @browser-settings="updateCurrentBrowserSettings"
          />

          <div v-if="currentSession?.goalPrompt" class="status-note">
            当前任务：{{ currentSession.goalPrompt }}<span v-if="currentSession.agentName"> · 执行干员 {{ currentSession.agentName }}</span>
          </div>

          <ExploreRecentEvents
            v-if="recentEvents.length"
            :events="recentEvents"
          />
          <div v-if="currentSession?.summary" class="report-block">
            <div class="stats-label">探索报告</div>
            <div class="report-text">{{ currentSession.summary }}</div>
          </div>

          <div v-if="currentSession?.discoveries?.length" class="discovery-block">
            <div class="stats-label">发现列表</div>
            <div class="discovery-list">
              <TravelDiscoveryItem
                v-for="(discovery, index) in currentSession.discoveries.slice(0, 12)"
                :key="`${discovery.url}-${index}`"
                :discovery="discovery"
                clickable
              />
            </div>
          </div>

          <div class="history-block">
            <TravelHistoryList :sessions="historyList" @select="viewSession" />
          </div>
        </div>
      </ScrollPanel>
    </div>

    <ForumSidebarRight />

    <ExploreHelpDialog v-model:visible="helpVisible" />

    <ExploreCreateDialog
      v-model:visible="createDialogVisible"
      v-model:goal-prompt="goalPrompt"
      v-model:selected-agent-id="selectedAgentId"
      v-model:time-limit-minutes="timeLimitMinutes"
      v-model:credit-limit="creditLimit"
      v-model:browser-visible="createBrowserVisible"
      v-model:browser-keep-open="createBrowserKeepOpen"
      :create-agent-options="createAgentOptions"
      :busy-agent-options="busyAgentOptions"
      :openclaw-agents="openclawAgents"
      :loading="loading"
      :can-start="canStartForSelectedAgent"
      @start="toggleExplore"
      @refresh="refreshAgentOptions"
    />

    <ExploreRawHistoryDialog
      v-model:visible="rawHistoryVisible"
      :loading="rawHistoryLoading"
      :messages="rawHistoryMessages"
    />
  </template>
</template>

<style scoped>
.main-col {
  background: rgba(20, 20, 20, 0.5);
  border-radius: 8px;
}

.page {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: min(760px, 100%);
  max-width: 760px;
  margin: 0 auto;
  padding: 28px 24px 20px;
  gap: 24px;
  box-sizing: border-box;
}

.title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.06em;
  align-self: flex-start;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  align-self: flex-start;
}

.help-btn {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  border: 1px solid rgba(212, 175, 55, 0.25);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(212, 175, 55, 0.88);
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.goal-block,
.report-block,
.discovery-block,
.history-block {
  width: 100%;
}

.create-toolbar {
  width: 100%;
}

.create-trigger-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(212, 175, 55, 0.28);
  background: transparent;
  color: rgba(255, 255, 255, 0.92);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.create-trigger-btn:hover {
  background: rgba(212, 175, 55, 0.06);
  border-color: rgba(212, 175, 55, 0.5);
  box-shadow: 0 0 0 1px rgba(212, 175, 55, 0.06);
}

.create-trigger-icon {
  font-size: 18px;
  line-height: 1;
}

.report-text {
  white-space: pre-wrap;
  line-height: 1.7;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.68);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  padding: 12px;
}

.discovery-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow: auto;
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

.status-note.warn {
  color: rgba(251, 191, 36, 0.82);
  background: rgba(251, 191, 36, 0.06);
  border-color: rgba(251, 191, 36, 0.18);
}

.status-note.danger {
  color: rgba(248, 113, 113, 0.9);
  background: rgba(248, 113, 113, 0.08);
  border-color: rgba(248, 113, 113, 0.2);
}

.explore-hint {
  font-size: 10px;
  color: rgba(52, 211, 153, 0.6);
  text-align: center;
  margin-top: -12px;
}

.stats-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}
</style>
