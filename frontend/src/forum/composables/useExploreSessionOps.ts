// 运行中会话操作域：终止 / 浏览器策略 / 原始历史（卷190-B4：从 ForumQuotaView.vue 纯搬移）
import { ref } from 'vue'
import API from '@/api/core'

interface SessionOpsDeps {
  currentSession: { readonly value: any }
  stopTravel: (sessionId: string) => Promise<unknown>
  updateTravelBrowserSettings: (sessionId: string, params: Record<string, any>) => Promise<unknown>
}

export function useExploreSessionOps(deps: SessionOpsDeps) {
  const { currentSession, stopTravel, updateTravelBrowserSettings } = deps

  const rawHistoryVisible = ref(false)
  const rawHistoryLoading = ref(false)
  const rawHistoryMessages = ref<Array<Record<string, any>>>([])

  async function stopCurrentSession() {
    if (!currentSession.value?.sessionId)
      return
    await stopTravel(currentSession.value.sessionId)
  }

  async function stopListedSession(sessionId: string) {
    await stopTravel(sessionId)
  }

  async function updateCurrentBrowserSettings(params: { browserVisible?: boolean, browserKeepOpen?: boolean }) {
    if (!currentSession.value?.sessionId)
      return
    await updateTravelBrowserSettings(currentSession.value.sessionId, params)
  }

  async function openRawHistory() {
    if (!currentSession.value?.sessionId || rawHistoryLoading.value)
      return
    rawHistoryLoading.value = true
    rawHistoryVisible.value = true
    try {
      const res = await API.getTravelSessionHistory(currentSession.value.sessionId, 120, true)
      rawHistoryMessages.value = res.messages || []
    }
    catch {
      rawHistoryMessages.value = []
    }
    finally {
      rawHistoryLoading.value = false
    }
  }

  return {
    rawHistoryVisible,
    rawHistoryLoading,
    rawHistoryMessages,
    stopCurrentSession,
    stopListedSession,
    updateCurrentBrowserSettings,
    openRawHistory,
  }
}
