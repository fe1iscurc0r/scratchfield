import type { ComputedRef } from 'vue'
import type { TravelSession } from '@/travel/types'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import coreApi from '@/api/core'

export const statusLabel: Record<string, string> = {
  pending: '准备中',
  running: '探索中',
  interrupted: '已中断',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

export function formatMinutes(m: number): string {
  const h = Math.floor(m / 60)
  const min = Math.round(m % 60)
  return h > 0 ? `${h}h ${min}m` : `${min}m`
}

export function formatDate(iso?: string): string {
  if (!iso)
    return '-'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const loading = ref(false)
const sessions = ref<TravelSession[]>([])
const selectedSessionId = ref<string | null>(null)
const lastRefreshedAt = ref<Date | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null
let consumerCount = 0

function isActiveStatus(status?: string) {
  return status === 'pending' || status === 'running'
}

function sortSessionsByFreshness(items: TravelSession[]) {
  return [...items].sort((a, b) => {
    const aTs = Date.parse(a.startedAt || a.createdAt || '') || 0
    const bTs = Date.parse(b.startedAt || b.createdAt || '') || 0
    return bTs - aTs
  })
}

function syncSelection() {
  const selectedExists = selectedSessionId.value && sessions.value.some(item => item.sessionId === selectedSessionId.value)
  if (selectedExists)
    return
  const sorted = sortSessionsByFreshness(sessions.value)
  selectedSessionId.value = sorted[0]?.sessionId || null
}

async function refreshSessions() {
  const res = await coreApi.getTravelSessions()
  sessions.value = res.sessions || []
  syncSelection()
  lastRefreshedAt.value = new Date()
}

function ensurePolling() {
  if (pollTimer)
    return
  pollTimer = setInterval(() => {
    void refreshSessions().catch(() => {})
  }, 10000)
}

function stopPolling() {
  if (!pollTimer)
    return
  clearInterval(pollTimer)
  pollTimer = null
}

export function useTravel() {
  const toast = useToast()

  const activeSessions = computed(() => sortSessionsByFreshness(
    sessions.value.filter(session => isActiveStatus(session.status)),
  ))
  const historyList = computed(() => sortSessionsByFreshness(
    sessions.value.filter(session => !isActiveStatus(session.status)),
  ))
  const travelSession = computed(() => {
    const selected = selectedSessionId.value
      ? sessions.value.find(session => session.sessionId === selectedSessionId.value)
      : null
    return selected || activeSessions.value[0] || historyList.value[0] || null
  })
  const isActive = computed(() => Boolean(travelSession.value && isActiveStatus(travelSession.value.status)))
  const isRunning = computed(() => travelSession.value?.status === 'running' || travelSession.value?.status === 'pending')
  const isCompleted = computed(() =>
    travelSession.value?.status === 'completed'
    || travelSession.value?.status === 'interrupted'
    || travelSession.value?.status === 'failed'
    || travelSession.value?.status === 'cancelled',
  )
  const timeProgress = computed(() => {
    if (!travelSession.value)
      return 0
    return Math.min(100, (travelSession.value.elapsedMinutes / travelSession.value.timeLimitMinutes) * 100)
  })
  const creditProgress = computed(() => {
    if (!travelSession.value)
      return 0
    return Math.min(100, (travelSession.value.creditsUsed / travelSession.value.creditLimit) * 100)
  })
  const lastUpdatedLabel = computed(() => {
    if (!lastRefreshedAt.value)
      return '-'
    const d = lastRefreshedAt.value
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
  })
  const activeSessionByAgentId: ComputedRef<Record<string, TravelSession>> = computed(() => {
    const byAgent: Record<string, TravelSession> = {}
    for (const session of activeSessions.value) {
      if (!session.agentId)
        continue
      if (!byAgent[session.agentId]) {
        byAgent[session.agentId] = session
      }
    }
    return byAgent
  })
  const latestSessionByAgentId: ComputedRef<Record<string, TravelSession>> = computed(() => {
    const byAgent: Record<string, TravelSession> = {}
    for (const session of sortSessionsByFreshness(sessions.value)) {
      if (!session.agentId)
        continue
      if (!byAgent[session.agentId]) {
        byAgent[session.agentId] = session
      }
    }
    return byAgent
  })

  async function startTravel(params: {
    agentId?: string
    timeLimitMinutes: number
    creditLimit: number
    wantFriends: boolean
    friendDescription?: string
    goalPrompt?: string
    deliverFullReport?: boolean
    deliverChannel?: string
    deliverTo?: string
    browserVisible?: boolean
    browserKeepOpen?: boolean
    browserIdleTimeoutSeconds?: number
  }): Promise<TravelSession | null> {
    loading.value = true
    try {
      const res = await coreApi.createTravelSession(params)
      selectedSessionId.value = res.sessionId
      await refreshSessions()
      ensurePolling()
      toast.add({ severity: 'success', summary: '探索已启动', detail: '后台会持续维护这个干员的探索任务', life: 3000 })
      return res.session || null
    }
    catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '启动失败'
      toast.add({ severity: 'error', summary: '启动失败', detail: msg, life: 5000 })
      return null
    }
    finally {
      loading.value = false
    }
  }

  async function stopTravel(sessionId?: string) {
    const targetId = sessionId || travelSession.value?.sessionId
    if (!targetId) {
      toast.add({ severity: 'warn', summary: '没有可停止的探索', detail: '当前没有选中的探索任务', life: 3000 })
      return
    }
    try {
      await coreApi.stopTravelSession(targetId)
      await refreshSessions()
      toast.add({ severity: 'info', summary: '探索已停止', detail: '该任务已标记为取消', life: 3000 })
    }
    catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '停止探索失败'
      toast.add({ severity: 'error', summary: '操作失败', detail: msg, life: 3000 })
    }
  }

  async function updateTravelBrowserSettings(sessionId: string, params: {
    browserVisible?: boolean
    browserKeepOpen?: boolean
    browserIdleTimeoutSeconds?: number
  }) {
    await coreApi.updateTravelSessionBrowser(sessionId, params)
    await refreshSessions()
  }

  function viewSession(session: TravelSession) {
    selectedSessionId.value = session.sessionId
  }

  function clearSelection() {
    selectedSessionId.value = null
    syncSelection()
  }

  function getActiveTravelForAgent(agentId?: string | null) {
    if (!agentId)
      return null
    return activeSessionByAgentId.value[agentId] || null
  }

  function getLatestTravelForAgent(agentId?: string | null) {
    if (!agentId)
      return null
    return latestSessionByAgentId.value[agentId] || null
  }

  function viewTravelForAgent(agentId?: string | null) {
    const session = getActiveTravelForAgent(agentId)
    if (!session)
      return null
    selectedSessionId.value = session.sessionId
    return session
  }

  onMounted(() => {
    consumerCount += 1
    void refreshSessions().catch(() => {})
    ensurePolling()
  })

  onUnmounted(() => {
    consumerCount = Math.max(0, consumerCount - 1)
    if (consumerCount === 0) {
      stopPolling()
    }
  })

  return {
    travelSession,
    activeSessions,
    historyList,
    isActive,
    isRunning,
    isCompleted,
    loading,
    timeProgress,
    creditProgress,
    lastUpdatedLabel,
    activeSessionByAgentId,
    startTravel,
    stopTravel,
    updateTravelBrowserSettings,
    viewSession,
    clearSelection,
    getActiveTravelForAgent,
    getLatestTravelForAgent,
    viewTravelForAgent,
    refreshSessions,
  }
}
