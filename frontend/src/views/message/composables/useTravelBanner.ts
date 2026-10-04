// 探索横幅与原始记录域：travel 横幅派生 + 成果报告 + 原始历史时间线（卷190-B3：从 MessageView.vue setup 纯搬移）
import type { Ref } from 'vue'
import { computed, ref, watch } from 'vue'
import API from '@/api/core'
import { useTravel } from '@/travel/composables/useTravel'
import { getActiveTab } from '@/utils/session'

export function useTravelBanner() {
  const { getActiveTravelForAgent, getLatestTravelForAgent } = useTravel()

  const activeAgentTravel = computed(() => {
    const tab = getActiveTab()
    return tab.type === 'agent' ? getActiveTravelForAgent(tab.instanceId) : null
  })
  const latestAgentTravel = computed(() => {
    const tab = getActiveTab()
    return tab.type === 'agent' ? getLatestTravelForAgent(tab.instanceId) : null
  })
  const completedAgentTravel = computed(() => {
    const travel = latestAgentTravel.value
    if (!travel || activeAgentTravel.value)
      return null
    return travel.status === 'completed' ? travel : null
  })
  const sendingTravelInstruction = ref(false)
  const rawTravelHistoryVisible = ref(false)
  const rawTravelHistoryLoading = ref(false)
  const rawTravelHistoryMessages = ref<Array<Record<string, any>>>([])
  const rawTravelHistoryError = ref('')
  const loadingCompletedTravelReport = ref(false)
  const completedTravelReport = ref<{
    sessionId: string
    exists: boolean
    path: string | null
    title?: string | null
    content: string | null
    missingReason?: 'not_generated' | 'missing'
  } | null>(null)
  const activeAgentTravelMeta = computed(() => {
    const travel = activeAgentTravel.value
    if (!travel)
      return ''
    const remainingMinutes = Math.max(0, Math.round(travel.timeLimitMinutes - travel.elapsedMinutes))
    const remainingCredits = Math.max(0, travel.creditLimit - travel.creditsUsed)
    return `${travel.discoveries.length} 个发现 · ${travel.uniqueSources || 0} 个来源 · 剩余 ${remainingMinutes} 分钟 / ${remainingCredits} 积分`
  })

  watch(completedAgentTravel, async (travel) => {
    if (!travel) {
      completedTravelReport.value = null
      return
    }
    loadingCompletedTravelReport.value = true
    try {
      const report = await API.getTravelSessionReport(travel.sessionId)
      completedTravelReport.value = {
        sessionId: travel.sessionId,
        exists: report.exists,
        path: report.path,
        title: report.title,
        content: report.content,
        missingReason: report.missingReason,
      }
    }
    catch {
      completedTravelReport.value = {
        sessionId: travel.sessionId,
        exists: false,
        path: travel.summaryReportPath || null,
        title: travel.summaryReportTitle || null,
        content: null,
        missingReason: 'missing',
      }
    }
    finally {
      loadingCompletedTravelReport.value = false
    }
  }, { immediate: true })

  async function openRawTravelHistory() {
    const travel = activeAgentTravel.value || completedAgentTravel.value
    if (!travel?.sessionId || rawTravelHistoryLoading.value)
      return
    rawTravelHistoryLoading.value = true
    rawTravelHistoryVisible.value = true
    rawTravelHistoryError.value = ''
    try {
      const history = await API.getTravelSessionHistory(travel.sessionId, 0, true)
      rawTravelHistoryMessages.value = history.messages || []
    }
    catch (e: any) {
      rawTravelHistoryMessages.value = []
      rawTravelHistoryError.value = e?.response?.data?.detail || e?.message || '读取原始探索记录失败'
    }
    finally {
      rawTravelHistoryLoading.value = false
    }
  }

  function stringifyRawHistoryValue(value: unknown) {
    if (value == null)
      return ''
    if (typeof value === 'string')
      return value
    try {
      return JSON.stringify(value, null, 2)
    }
    catch {
      return String(value)
    }
  }

  function rawHistoryEntryMessage(entry: Record<string, any>) {
    return entry?.message && typeof entry.message === 'object'
      ? entry.message as Record<string, any>
      : null
  }

  function extractRawHistoryPreview(content: unknown) {
    if (typeof content === 'string')
      return content.trim()
    if (!Array.isArray(content))
      return ''
    const parts = content.flatMap((item) => {
      if (!item || typeof item !== 'object')
        return []
      if (item.type === 'text' && typeof item.text === 'string')
        return [item.text.trim()]
      if (item.type === 'toolCall')
        return [`[tool call] ${String(item.name || 'unknown')}`]
      return []
    }).filter(Boolean)
    return parts.join(' ').trim()
  }

  function rawHistoryEntryTimestamp(entry: Record<string, any>) {
    const raw = entry?.timestamp
    if (typeof raw === 'number')
      return new Date(raw).toTimeString().slice(0, 8)
    const text = String(raw || '')
    if (text.includes('T'))
      return text.slice(11, 19)
    return text || '--:--:--'
  }

  function parsePossibleJson(text: string) {
    const trimmed = text.trim()
    const firstChar = trimmed.charAt(0)
    if (!trimmed || !['{', '['].includes(firstChar))
      return null
    try {
      return JSON.parse(trimmed)
    }
    catch {
      return null
    }
  }

  function truncateHistoryText(text: string, maxChars = 2400) {
    const normalized = text.trim()
    if (!normalized)
      return '无内容'
    if (normalized.length <= maxChars)
      return normalized
    return `${normalized.slice(0, maxChars)}\n\n...已截断 ${normalized.length - maxChars} 个字符`
  }

  function formatTravelToolResult(toolName: string, text: string) {
    const parsed = parsePossibleJson(text)
    if (toolName === 'travel_state' && parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const state = parsed as Record<string, any>
      return [
        `状态: ${state.status || '-'}`,
        `阶段: ${state.phase || '-'}`,
        `发现: ${Array.isArray(state.discoveries) ? state.discoveries.length : 0} 条`,
        `来源: ${state.uniqueSources ?? (Array.isArray(state.sources) ? state.sources.length : 0)} 个`,
        `积分: ${state.creditsUsed ?? 0} / ${state.creditLimit ?? 0}`,
        `时间: ${state.elapsedMinutes ?? 0} / ${state.timeLimitMinutes ?? 0} 分钟`,
      ].join('\n')
    }
    if (toolName === 'travel_summary' && parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const result = parsed as Record<string, any>
      return [
        `标题: ${result.title || '-'}`,
        `文件: ${result.file_path || result.path || '-'}`,
        `大小: ${result.bytes ?? '-'} bytes`,
      ].join('\n')
    }
    return truncateHistoryText(text)
  }

  const rawTravelHistoryTimeline = computed(() => {
    const items: Array<{
      id: string
      kind: 'assistant' | 'tool_call' | 'tool_result'
      title: string
      time: string
      text: string
    }> = []

    rawTravelHistoryMessages.value.forEach((entry, index) => {
      const message = rawHistoryEntryMessage(entry)
      if (!message)
        return

      const role = String(message.role || '').trim()
      const time = rawHistoryEntryTimestamp(entry)

      if (role === 'assistant') {
        const content = Array.isArray(message.content) ? message.content : []
        let textBuffer: string[] = []
        const flushAssistantText = () => {
          const text = textBuffer.join('\n\n').trim()
          textBuffer = []
          if (!text)
            return
          items.push({
            id: `${index}-assistant-${items.length}`,
            kind: 'assistant',
            title: 'AI 回复',
            time,
            text,
          })
        }

        for (const part of content) {
          if (!part || typeof part !== 'object')
            continue
          if (part.type === 'text' && typeof part.text === 'string' && part.text.trim()) {
            textBuffer.push(part.text.trim())
            continue
          }
          if (part.type === 'toolCall') {
            flushAssistantText()
            items.push({
              id: `${index}-toolcall-${String(part.id || items.length)}`,
              kind: 'tool_call',
              title: `调度工具 · ${String(part.name || 'unknown')}`,
              time,
              text: stringifyRawHistoryValue(part.arguments || {}),
            })
          }
        }

        if (!content.length && typeof message.content === 'string' && message.content.trim())
          textBuffer.push(message.content.trim())

        flushAssistantText()
        return
      }

      if (role === 'toolResult' || role === 'tool_result') {
        const toolName = String(message.toolName || 'tool')
        const text = extractRawHistoryPreview(message.content)
        items.push({
          id: `${index}-toolresult-${toolName}`,
          kind: 'tool_result',
          title: `工具结果 · ${toolName}`,
          time,
          text: formatTravelToolResult(toolName, text),
        })
      }
    })

    return items
  })

  return {
    activeAgentTravel,
    completedAgentTravel,
    sendingTravelInstruction,
    rawTravelHistoryVisible,
    rawTravelHistoryLoading,
    rawTravelHistoryMessages,
    rawTravelHistoryError,
    loadingCompletedTravelReport,
    completedTravelReport,
    activeAgentTravelMeta,
    rawTravelHistoryTimeline,
    openRawTravelHistory,
  }
}

export type { Ref }
