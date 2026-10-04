// 配额仪表板派生态：全部展示 computed（卷190-B4：从 ForumQuotaView.vue 纯搬移）
import type { Ref } from 'vue'
import { computed, watch } from 'vue'
import { ACCESS_TOKEN } from '@/api'
import { backendConnected } from '@/utils/config'

interface DashboardDeps {
  profile: Ref<any>
  travelSession: Ref<any>
  activeSessions: Ref<any[]>
  historyList: Ref<any[]>
  reload: () => Promise<unknown> | unknown
}

export function useQuotaDashboard(deps: DashboardDeps) {
  const { profile, travelSession, activeSessions, historyList, reload } = deps

  const exploring = computed(() => activeSessions.value.length > 0)
  const currentSession = computed(() =>
    travelSession.value || activeSessions.value[0] || historyList.value[0] || null)

  const realCredits = computed(() => profile.value?.creditsBalance ?? 0)
  const effectiveDailyBudget = computed(() => profile.value?.quota?.dailyBudget ?? 1000)
  const effectiveUsedToday = computed(() => profile.value?.quota?.usedToday ?? 0)
  const currentFindings = computed(() => currentSession.value?.discoveries?.length ?? 0)
  const currentSources = computed(() => currentSession.value?.uniqueSources ?? 0)
  const currentSocial = computed(() => currentSession.value?.socialInteractions?.length ?? 0)

  const phaseLabel = computed(() => {
    switch (currentSession.value?.phase) {
      case 'bootstrapping': return '正在准备运行环境'
      case 'running': return '正在搜索与浏览'
      case 'wrapping_up': return '正在收束'
      case 'finalizing': return '正在整理总结'
      case 'publishing': return '正在发布论坛摘要'
      case 'delivering_report': return '正在回传报告'
      case 'notifying': return '正在发送通知'
      case 'completed': return '已完成'
      case 'interrupted': return '已中断'
      case 'failed': return '失败'
      case 'cancelled': return '已取消'
      default: return '未开始'
    }
  })

  const remainingMinutes = computed(() => {
    if (!currentSession.value)
      return 0
    return Math.max(0, currentSession.value.timeLimitMinutes - currentSession.value.elapsedMinutes)
  })

  const remainingCredits = computed(() => {
    if (!currentSession.value)
      return 0
    return Math.max(0, currentSession.value.creditLimit - currentSession.value.creditsUsed)
  })

  const recentEvents = computed(() =>
    [...(currentSession.value?.progressEvents || [])].slice(-8).reverse())

  const statusTone = computed(() => {
    const status = currentSession.value?.status
    if (status === 'failed' || status === 'cancelled')
      return 'danger'
    if (status === 'interrupted')
      return 'warn'
    if (status === 'completed')
      return 'ok'
    return 'active'
  })

  const statusLabel = computed(() => {
    switch (currentSession.value?.status) {
      case 'pending': return '准备中'
      case 'running': return '探索中'
      case 'interrupted': return '已中断'
      case 'completed': return '已完成'
      case 'failed': return '失败'
      case 'cancelled': return '已取消'
      default: return '未开始'
    }
  })

  const sessionNotice = computed(() => {
    const session = currentSession.value
    if (!session)
      return null
    if (session.status === 'interrupted' && session.interruptedReason === 'auth_expired') {
      return {
        tone: 'warn',
        text: '当前登录态已过期，探索已自动挂起并落盘。重新登录后可继续恢复。',
      }
    }
    if (session.status === 'failed' && session.error) {
      return {
        tone: 'danger',
        text: session.error,
      }
    }
    return null
  })

  const quotaRemaining = computed(() => {
    return Math.max(0, effectiveDailyBudget.value - effectiveUsedToday.value)
  })

  const quotaPercent = computed(() => {
    if (effectiveDailyBudget.value === 0)
      return 0
    return Math.round((quotaRemaining.value / effectiveDailyBudget.value) * 100)
  })

  // SVG 圆环
  const RING_R = 58
  const RING_C = 2 * Math.PI * RING_R
  const ringOffset = computed(() => RING_C * (1 - quotaPercent.value / 100))

  watch([backendConnected, ACCESS_TOKEN], ([connected, token]) => {
    if (connected && token && !profile.value) {
      void reload()
    }
  })

  return {
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
    RING_R,
    RING_C,
    ringOffset,
  }
}
