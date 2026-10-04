// 陆墨主会话流：chatStream 家族 + TTS 句子缓冲工具 + 工具事件构造（卷190-B3：从 MessageView.vue 非 setup script 块纯搬移）
// ⚠️ 导出兼容红线：MessageView.vue 的非 setup script 块 re-export 本文件的 chatStream，
//    外部 `import { chatStream } from '@/views/MessageView.vue'` 的调用方（FloatingView 等）不受影响。
import { computed, ref } from 'vue'
import { ACCESS_TOKEN, authExpired } from '@/api'
import API from '@/api/core'
import { CONFIG } from '@/utils/config'
import { live2dState } from '@/utils/live2dController'
import { CURRENT_SESSION_ID, IS_TEMPORARY_SESSION, MESSAGES } from '@/utils/session'
import { isPlaying, queueSpeak, stop as stopTTS } from '@/utils/tts'
import { TtsSentenceBuffer } from '@/utils/ttsText'

const isSending = ref(false)
const messageQueue: Array<{ content: string, options?: any }> = []
const ttsEnabled = computed(() => CONFIG.value.system.voice_enabled)

export function appendTtsText(buffer: TtsSentenceBuffer, text: string): void {
  if (!ttsEnabled.value) {
    buffer.clear()
    return
  }
  for (const sentence of buffer.append(text))
    queueSpeak(sentence)
}

export function replaceTtsText(buffer: TtsSentenceBuffer, text: string): void {
  if (!ttsEnabled.value) {
    buffer.clear()
    return
  }

  // 原始流可能已经包含文本式工具调用，先停止再使用服务端清理后的正文重建队列。
  stopTTS()
  buffer.replace(text)
}

export function flushTtsText(buffer: TtsSentenceBuffer): void {
  if (!ttsEnabled.value) {
    buffer.clear()
    return
  }
  const remainder = buffer.flush()
  if (remainder)
    queueSpeak(remainder)
}

export function toolEventName(item: Record<string, any>): string {
  const service = item.service_name || item.agentType || '工具'
  return item.tool_name ? `${service}: ${item.tool_name}` : service
}

// 工具事件的构造收敛在两处（会话流 + 干员流共四种推入点），
// 避免事件形状今后在多处漂移。
export function pushToolCallEvent(msg: { toolEvents?: any[] }, call: any) {
  msg.toolEvents = msg.toolEvents || []
  msg.toolEvents.push({ type: 'tool_call', name: toolEventName(call), args: call })
}

export function pushToolResultEvent(msg: { toolEvents?: any[] }, result: any) {
  msg.toolEvents = msg.toolEvents || []
  msg.toolEvents.push({
    type: 'tool_result',
    name: toolEventName(result),
    isError: result.status !== 'success',
    result: result.result,
  })
}

async function processQueue() {
  if (messageQueue.length === 0 || isSending.value)
    return

  const { content, options } = messageQueue.shift()!
  await chatStreamInternal(content, options)
}

export function chatStream(content: string, options?: { skill?: string, images?: string[], voiceInput?: boolean }) {
  // 用户发送新消息时，立即中止上一次的 TTS 播放
  stopTTS()

  // 立即显示用户消息
  MESSAGES.value.push({ role: 'user', content: options?.images?.length ? `[截图x${options.images.length}] ${content}` : content })

  // 将消息加入队列
  messageQueue.push({ content, options })
  processQueue()
}

async function chatStreamInternal(content: string, options?: { skill?: string, images?: string[], voiceInput?: boolean }) {
  isSending.value = true

  // 预先推入 assistant 消息（立即显示，不等 API 响应）
  MESSAGES.value.push({
    role: 'assistant',
    content: '',
    reasoning: '',
    generating: true,
    status: options?.voiceInput ? '理解话语中' : undefined,
    toolEvents: [],
  })
  const message = MESSAGES.value.at(-1)!
  // 开启语音时在流式输出中逐句送入 TTS 队列，文本始终实时显示。
  const ttsBuffer = new TtsSentenceBuffer()
  let contentBuf = ''
  const pushContent = (text: string) => {
    contentBuf += text
    message.content = contentBuf
  }

  live2dState.value = 'thinking'
  let compressTimer: ReturnType<typeof setTimeout> | undefined
  // 记录当前轮次 content 流的起始位置，content_clean 只替换当前轮的 LLM 输出
  let roundContentStart = 0

  API.chatStream(content, {
    sessionId: CURRENT_SESSION_ID.value ?? undefined,
    disableTTS: true,
    skill: options?.skill,
    images: options?.images,
    temporary: IS_TEMPORARY_SESSION.value || undefined,
  }).then(async ({ sessionId, response }) => {
    if (sessionId) {
      CURRENT_SESSION_ID.value = sessionId
    }

    for await (const chunk of response) {
      if (chunk.type === 'reasoning') {
        message.reasoning = (message.reasoning || '') + chunk.text
      }
      else if (chunk.type === 'content') {
        pushContent(chunk.text || '')
        appendTtsText(ttsBuffer, chunk.text || '')
      }
      else if (chunk.type === 'content_clean') {
        // 仅替换当前轮次的 LLM 输出（从 roundContentStart 开始），保留之前轮次的工具通知
        contentBuf = contentBuf.substring(0, roundContentStart) + (chunk.text || '')
        message.content = contentBuf
        replaceTtsText(ttsBuffer, chunk.text || '')
      }
      else if (chunk.type === 'tool_calls') {
        // 工具执行可能耗时，先朗读清理后的引导语。
        flushTtsText(ttsBuffer)
        // 显示工具调用状态
        const calls = chunk.calls || []
        const callDesc = calls.map((c: any) => toolEventName(c)).join(', ')
        message.status = callDesc ? `正在执行工具: ${callDesc}` : '正在执行工具'
        for (const call of calls) {
          pushToolCallEvent(message, call)
        }
        // OpenClaw 工具可能耗时较长，添加提示
        const hasOpenclaw = calls.some((c: any) => {
          const name = (c.service_name || c.agentType || '').toLowerCase()
          return name.includes('openclaw') || name.includes('agent')
        })
        if (hasOpenclaw) {
          pushContent('> ⏳ OpenClaw 工具处理可能会比较久，预计需要两分钟\n')
        }
      }
      else if (chunk.type === 'tool_results') {
        for (const result of chunk.results || []) {
          pushToolResultEvent(message, result)
        }
        // 工具结果追加完毕，更新下一轮 content 的起始位置
        roundContentStart = contentBuf.length
      }
      else if (chunk.type === 'round_start' && (chunk.round ?? 0) > 1) {
        // 多轮分隔
        pushContent('\n---\n\n')
        // 新一轮开始，更新 content 起始位置
        roundContentStart = contentBuf.length
      }
      else if (chunk.type === 'round_end') {
        flushTtsText(ttsBuffer)
      }
      else if (chunk.type === 'token_refreshed') {
        // 后端刷新了 token，同步到前端（防止后续轮询请求用旧 token 覆盖）
        if (chunk.text) {
          ACCESS_TOKEN.value = chunk.text
        }
      }
      else if (chunk.type === 'auth_expired') {
        // 后端 LLM 认证失败且刷新也失败，触发重新登录
        authExpired.value = true
        pushContent(chunk.text || '登录已过期，请重新登录')
      }
      else if (chunk.type === 'status') {
        message.status = chunk.text || ''
      }
      else if (chunk.type === 'intent_result') {
        const tools = (chunk as any).tools || []
        if (tools.length > 0) {
          message.status = `调度: ${tools.join(', ')}`
        }
      }
      else if (chunk.type === 'pre_search_start') {
        message.status = `搜索: ${chunk.text || ''}`
      }
      else if (chunk.type === 'pre_search_end') {
        message.status = chunk.text || '搜索完成'
      }
      else if (chunk.type === 'compress_start' || chunk.type === 'compress_progress' || chunk.type === 'compress_end') {
        // 上下文压缩进度提示（覆盖式显示，直接写 message.content 不走缓冲）
        message.content = `> ${chunk.text}\n\n`
        if (chunk.type === 'compress_end') {
          compressTimer = setTimeout(() => {
            message.content = ''
          }, 1200)
        }
      }
      else if (chunk.type === 'compress_info') {
        // 运行时压缩完成，在当前 assistant 消息前插入 info 标记
        if (compressTimer) {
          clearTimeout(compressTimer)
          compressTimer = undefined
        }
        message.content = ''
        const idx = MESSAGES.value.indexOf(message)
        if (idx > 0) {
          MESSAGES.value.splice(idx, 0, { role: 'info', content: chunk.text || '【已压缩上下文】' })
        }
      }
      window.dispatchEvent(new CustomEvent('token', { detail: chunk.text || '' }))
    }

    // 清理生成状态（文本已实时显示，无需等待 TTS）
    delete message.generating
    delete message.status
    if (!message.reasoning)
      delete message.reasoning

    flushTtsText(ttsBuffer)
    if (!isPlaying.value) {
      live2dState.value = 'idle'
    }
  }).catch((err) => {
    live2dState.value = 'idle'
    message.content = `Error: ${err.message}`
    delete message.generating
    delete message.status
    if (message.reasoning === '')
      delete message.reasoning
  }).finally(() => {
    isSending.value = false
    processQueue()
  })
}
