import type { Ref } from 'vue'
// 发送分发域：sendMessage/dispatchToActiveTab/sendToAgent（干员双通道流）（卷190-B3：从 MessageView.vue setup 纯搬移）
import type { ChatTab, Message } from '@/utils/session'
import { nextTick, ref } from 'vue'
import API from '@/api/core'
import { activeTabId, agentContacts, getActiveTab, MESSAGES } from '@/utils/session'
import { stop as stopTTS } from '@/utils/tts'
import { TtsSentenceBuffer } from '@/utils/ttsText'
import {
  appendTtsText,
  chatStream,
  flushTtsText,
  pushToolCallEvent,
  pushToolResultEvent,
  replaceTtsText,
  toolEventName,
} from './useChatStream'

interface DispatcherDeps {
  input: Ref<string | undefined>
  scrollToBottom: () => void
  scrollToBottomIfPinned: () => void
  activeAgentTravel: { readonly value: any }
}

export function useSendDispatcher(deps: DispatcherDeps) {
  const { input, scrollToBottom, scrollToBottomIfPinned, activeAgentTravel } = deps
  const sendingTravelInstruction = ref(false)

  function saveAgentTabMessages(tab: ChatTab) {
    if (!tab.instanceId)
      return
    const storageKey = `agent_history_${tab.instanceId}`
    localStorage.setItem(storageKey, JSON.stringify(tab.messages))
  }

  function pushSystemMessage(content: string): Message {
    const message: Message = { role: 'system', content }
    const tab = getActiveTab()
    if (tab.type === 'agent') {
      tab.messages.push(message)
      saveAgentTabMessages(tab)
    }
    else {
      MESSAGES.value.push(message)
    }
    nextTick().then(scrollToBottom)
    return message
  }

  function dispatchToActiveTab(content: string, options?: { skill?: string, images?: string[], voiceInput?: boolean }) {
    const tab = getActiveTab()
    if (tab.type === 'agent') {
      void sendToAgent(tab, content, options)
      return
    }
    chatStream(content, options)
    nextTick().then(scrollToBottom)
  }

  // ── 发送分发 ──
  function sendMessage() {
    const tab = getActiveTab()
    if (!input.value?.trim())
      return

    if (tab.type === 'agent') {
      sendToAgent(tab, input.value.trim())
      input.value = ''
      return
    }
    // 陆墨 tab → 原有 chatStream
    chatStream(input.value)
    nextTick().then(scrollToBottom)
    input.value = ''
  }

  async function sendTravelInstruction() {
    const travel = activeAgentTravel.value
    const message = input.value?.trim()
    if (!travel || !message || sendingTravelInstruction.value)
      return
    sendingTravelInstruction.value = true
    try {
      await API.sendTravelInstruction(travel.sessionId, message)
      pushSystemMessage(`已追加到探索任务：${message}`)
      input.value = ''
    }
    catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || '追加探索指令失败'
      pushSystemMessage(`追加探索指令失败：${detail}`)
    }
    finally {
      sendingTravelInstruction.value = false
    }
  }

  async function sendToAgent(tab: ChatTab, msg: string, options?: { skill?: string, images?: string[], voiceInput?: boolean }) {
    stopTTS()

    if (!tab.instanceId) {
      tab.messages.push({ role: 'system', content: '干员实例未就绪，请稍后再试' })
      return
    }
    if (tab.engine === 'lumo-core') {
      tab.messages.push({ role: 'user', content: msg })
      nextTick().then(scrollToBottom)

      tab.messages.push({
        role: 'assistant',
        content: '',
        reasoning: '',
        generating: true,
        status: options?.voiceInput ? '理解话语中' : '思考中',
        sender: tab.name,
        toolEvents: [],
      })
      const assistantMsg = tab.messages.at(-1)!
      let contentBuf = ''
      let roundContentStart = 0
      const ttsBuffer = new TtsSentenceBuffer()

      try {
        const { sessionId, response } = await API.chatStream(msg, {
          sessionId: tab.sessionId,
          agentId: tab.instanceId,
          disableTTS: true,
          skill: options?.skill,
          images: options?.images,
          temporary: false,
        })

        if (sessionId) {
          tab.sessionId = sessionId
          localStorage.setItem(`agent_session_${tab.instanceId}`, sessionId)
        }

        for await (const chunk of response) {
          if (chunk.type === 'reasoning') {
            assistantMsg.reasoning = (assistantMsg.reasoning || '') + (chunk.text || '')
          }
          else if (chunk.type === 'content') {
            contentBuf += chunk.text || ''
            assistantMsg.content = contentBuf
            appendTtsText(ttsBuffer, chunk.text || '')
          }
          else if (chunk.type === 'content_clean') {
            contentBuf = contentBuf.substring(0, roundContentStart) + (chunk.text || '')
            assistantMsg.content = contentBuf
            replaceTtsText(ttsBuffer, chunk.text || '')
          }
          else if (chunk.type === 'round_start' && (chunk.round ?? 0) > 1) {
            contentBuf += '\n---\n\n'
            assistantMsg.content = contentBuf
            roundContentStart = contentBuf.length
          }
          else if (chunk.type === 'tool_calls') {
            flushTtsText(ttsBuffer)
            const calls = chunk.calls || []
            assistantMsg.status = calls.length > 0
              ? `调度工具: ${calls.map(c => toolEventName(c)).join(', ')}`
              : '调度工具中'
            for (const call of calls) {
              pushToolCallEvent(assistantMsg, call)
            }
          }
          else if (chunk.type === 'tool_results') {
            for (const result of chunk.results || []) {
              pushToolResultEvent(assistantMsg, result)
            }
            roundContentStart = contentBuf.length
          }
          else if (chunk.type === 'status') {
            assistantMsg.status = chunk.text || ''
          }
          else if (chunk.type === 'round_end') {
            flushTtsText(ttsBuffer)
          }
          else if (chunk.type === 'compress_info') {
            const idx = tab.messages.indexOf(assistantMsg)
            if (idx > 0) {
              tab.messages.splice(idx, 0, { role: 'info', content: chunk.text || '【已压缩上下文】' })
            }
          }
          else if (chunk.type === 'auth_expired') {
            assistantMsg.content = chunk.text || '登录已过期，请重新登录'
          }
          nextTick().then(scrollToBottomIfPinned)
        }
        flushTtsText(ttsBuffer)
      }
      catch (e: any) {
        const detail = e?.response?.data?.detail || e?.message || e
        assistantMsg.content = `发送失败: ${detail}`
      }

      delete assistantMsg.generating
      delete assistantMsg.status
      if (!assistantMsg.reasoning) {
        delete assistantMsg.reasoning
      }
      saveAgentTabMessages(tab)
      if (activeTabId.value !== tab.id) {
        tab.unread++
      }
      nextTick().then(scrollToBottom)
      return
    }

    tab.messages.push({ role: 'user', content: msg })
    nextTick().then(scrollToBottom)

    tab.messages.push({ role: 'assistant', content: '', generating: true, status: '思考中', sender: tab.name, toolEvents: [] })
    const assistantMsg = tab.messages.at(-1)!
    const ttsBuffer = new TtsSentenceBuffer()
    let receivedContent = false

    try {
      // 流式接收回复（使用新 API，内部自动 ensure_running）
      for await (const chunk of API.streamToAgent(tab.instanceId, msg)) {
        if (chunk.type === 'status') {
          assistantMsg.status = chunk.text
        }
        else if (chunk.type === 'content') {
          receivedContent = true
          assistantMsg.content += chunk.text
          appendTtsText(ttsBuffer, chunk.text)
        }
        else if (chunk.type === 'done') {
          assistantMsg.content = chunk.text // 用完整文本覆盖，防止拼接偏差
          if (!receivedContent)
            ttsBuffer.replace(chunk.text)
          flushTtsText(ttsBuffer)
        }
        else if (chunk.type === 'error') {
          assistantMsg.content = `错误: ${chunk.text}`
        }
        else if (chunk.type === 'tool_call') {
          assistantMsg.status = `🔧 ${chunk.name || '工具调用中'}...`
          assistantMsg.toolEvents = assistantMsg.toolEvents || []
          assistantMsg.toolEvents.push({
            type: 'tool_call',
            name: chunk.name || '工具',
            toolCallId: chunk.toolCallId,
            args: chunk.args,
          })
        }
        else if (chunk.type === 'tool_result') {
          assistantMsg.status = `${chunk.isError ? '❌' : '✅'} ${chunk.name || '工具'} ${chunk.isError ? '失败' : '完成'}`
          assistantMsg.toolEvents = assistantMsg.toolEvents || []
          assistantMsg.toolEvents.push({
            type: 'tool_result',
            name: chunk.name || '工具',
            toolCallId: chunk.toolCallId,
            isError: chunk.isError,
            result: chunk.result ?? chunk.text,
          })
        }
        nextTick().then(scrollToBottomIfPinned)
      }
      flushTtsText(ttsBuffer)
    }
    catch (e: any) {
      const detail = e?.response?.data?.detail || e.message || e
      assistantMsg.content = `发送失败: ${detail}`
    }

    delete assistantMsg.generating
    delete assistantMsg.status

    // 保存干员对话历史到 localStorage
    saveAgentTabMessages(tab)

    // 非活跃 tab → 未读+1
    if (activeTabId.value !== tab.id) {
      tab.unread++
    }

    nextTick().then(scrollToBottom)
  }

  return {
    sendingTravelInstruction,
    pushSystemMessage,
    dispatchToActiveTab,
    sendMessage,
    sendTravelInstruction,
    sendToAgent,
  }
}

// agentContacts 供壳使用（从 session re-export 保持引用路径集中）
export { agentContacts }
export type { Ref }
