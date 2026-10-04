// 会话历史域：列表加载/切换/删除/新建（卷190-B3：从 MessageView.vue setup 纯搬移）
import { nextTick, ref } from 'vue'
import API from '@/api/core'
import { CURRENT_SESSION_ID, newSession, switchSession } from '@/utils/session'

export function useSessionHistory(onSwitched: () => void) {
  const showHistory = ref(false)
  const sessions = ref<Array<{
    sessionId: string
    createdAt: string
    lastActiveAt: string
    conversationRounds: number
    temporary: boolean
  }>>([])
  const loadingSessions = ref(false)

  async function fetchSessions() {
    loadingSessions.value = true
    try {
      const res = await API.getSessions()
      sessions.value = res.sessions ?? []
    }
    catch {
      sessions.value = []
    }
    loadingSessions.value = false
  }

  function toggleHistory() {
    showHistory.value = !showHistory.value
    if (showHistory.value) {
      fetchSessions()
    }
  }

  async function handleSwitchSession(id: string) {
    await switchSession(id)
    showHistory.value = false
    nextTick().then(onSwitched)
  }

  async function handleDeleteSession(id: string) {
    try {
      await API.deleteSession(id)
      sessions.value = sessions.value.filter(s => s.sessionId !== id)
      if (CURRENT_SESSION_ID.value === id) {
        newSession()
      }
    }
    catch { /* ignore */ }
  }

  function handleNewSession() {
    newSession()
    showHistory.value = false
  }

  return {
    showHistory,
    sessions,
    loadingSessions,
    fetchSessions,
    toggleHistory,
    handleSwitchSession,
    handleDeleteSession,
    handleNewSession,
  }
}
