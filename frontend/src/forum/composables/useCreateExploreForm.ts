// 新建探索表单域：表单状态 + 干员选项派生 + watch 联动 + 发起动作（卷190-B4：从 ForumQuotaView.vue 纯搬移）
import type { Ref } from 'vue'
import { computed, ref, watch } from 'vue'
import { agentContacts, loadAgentContacts } from '@/utils/session'

interface CreateFormDeps {
  activeSessions: Ref<any[]>
  activeSessionByAgentId: Ref<Record<string, any>>
  /** 每日剩余配额（useQuotaDashboard.quotaRemaining，壳组装时传入） */
  quotaRemaining: { readonly value: number }
  effectiveDailyBudget: { readonly value: number }
  refreshSessions: () => Promise<unknown> | unknown
  startTravel: (opts: any) => Promise<any>
}

export function useCreateExploreForm(deps: CreateFormDeps) {
  const { activeSessions, activeSessionByAgentId, quotaRemaining, effectiveDailyBudget, refreshSessions, startTravel } = deps

  const createDialogVisible = ref(false)
  const goalPrompt = ref('追踪 AI、技术与互联网的最新热点，优先关注仍在持续发酵的话题和一手来源')
  const selectedAgentId = ref('')
  const timeLimitMinutes = ref(120)
  const creditLimit = ref(800)
  const createBrowserVisible = ref(false)
  const createBrowserKeepOpen = ref(false)

  const openclawAgents = computed(() =>
    agentContacts.value.filter(agent => (agent.engine || 'openclaw') === 'openclaw'))
  const activeAgentIdSet = computed(() =>
    new Set(activeSessions.value.map(session => session.agentId).filter(Boolean)))
  const busyAgentOptions = computed(() =>
    openclawAgents.value.filter(agent => activeAgentIdSet.value.has(agent.id)))
  const createAgentOptions = computed(() =>
    openclawAgents.value.filter(agent => !activeAgentIdSet.value.has(agent.id)))
  const selectedAgentSession = computed(() =>
    selectedAgentId.value ? activeSessionByAgentId.value[selectedAgentId.value] || null : null)
  const canStartForSelectedAgent = computed(() =>
    !!selectedAgentId.value && !selectedAgentSession.value)

  watch(createDialogVisible, (visible) => {
    if (!visible)
      return
    void loadAgentContacts()
    void refreshSessions()
  })

  watch(createAgentOptions, (agents) => {
    if (!selectedAgentId.value && agents.length > 0) {
      selectedAgentId.value = agents[0]!.id
    }
    if (selectedAgentId.value) {
      const stillExists = agents.some(agent => agent.id === selectedAgentId.value)
      if (!stillExists) {
        selectedAgentId.value = agents[0]?.id || ''
      }
    }
  }, { immediate: true })

  watch(
    () => quotaRemaining.value,
    (remaining) => {
      creditLimit.value = Math.max(100, Math.min(Math.round(remaining || effectiveDailyBudget.value || 800), 10000))
    },
    { immediate: true },
  )

  async function refreshAgentOptions() {
    await Promise.all([
      loadAgentContacts(),
      refreshSessions(),
    ])
  }

  async function toggleExplore(): Promise<boolean> {
    const result = await startTravel({
      agentId: selectedAgentId.value || undefined,
      timeLimitMinutes: timeLimitMinutes.value,
      creditLimit: creditLimit.value,
      wantFriends: false,
      goalPrompt: goalPrompt.value || undefined,
      browserVisible: createBrowserVisible.value,
      browserKeepOpen: createBrowserKeepOpen.value,
      browserIdleTimeoutSeconds: 300,
    })
    if (result) {
      createDialogVisible.value = false
      return true
    }
    return false
  }

  return {
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
  }
}
