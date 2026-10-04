import type { DomainShape } from './_context'
import type { StreamChunk } from './_internals'
/**
 * chat 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import { ACCESS_TOKEN, aiter, axios, decodeStreamChunk, readerToMessageStream, toSnake } from './_internals'

export const chatMethods = {
  chat(message: string, options?: {
    sessionId?: string
    agentId?: string
    useSelfGame?: boolean
    skipIntentAnalysis?: boolean
  }): Promise<{
    status: 'success'
    response: string
    sessionId?: string
  }> {
    return this.instance.post('/chat', { message, ...options })
  },

  async chatStream(message: string, options?: {
    sessionId?: string
    agentId?: string
    returnAudio?: boolean
    disableTTS?: boolean
    skipIntentAnalysis?: boolean
    skill?: string
    images?: string[]
    temporary?: boolean
  }): Promise<{
    sessionId?: string
    response: AsyncGenerator<StreamChunk>
  }> {
    const streamBody = JSON.stringify(toSnake({ message, ...options }))
    const doFetch = (token: string | null) => fetch(`${this.endpoint}/chat/stream`, {
      method: 'POST',
      headers: {
        'Accept': 'text/event-stream',
        'Authorization': token ? `Bearer ${token}` : '',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
      },
      body: streamBody,
    })

    let resp = await doFetch(ACCESS_TOKEN.value)
    if (resp.status === 401) {
      // fetch 不走 axios 401 拦截器：token 失效时自行刷新一次并重试
      try {
        const legacyToken = localStorage.getItem('lumo-refresh-token')
        const refreshResp = await axios.post<{ access_token: string }>(
          `${this.endpoint}/auth/refresh`,
          legacyToken ? { refresh_token: legacyToken } : {},
        )
        if (refreshResp.data?.access_token) {
          ACCESS_TOKEN.value = refreshResp.data.access_token
          localStorage.removeItem('lumo-refresh-token')
          resp = await doFetch(ACCESS_TOKEN.value)
        }
      }
      catch { /* 刷新失败，下方统一报错 */ }
    }
    if (!resp.ok) {
      throw new Error(`chatStream 请求失败: HTTP ${resp.status}${resp.status === 401 ? '（登录状态已失效，请重新登录）' : ''}`)
    }
    const { body } = { body: resp.body }

    const reader = await body?.getReader()
    if (!reader) {
      throw new Error('Failed to get reader')
    }
    const messageStream = readerToMessageStream(reader)
    const { value } = await messageStream.next()
    if (!value?.startsWith('session_id: ')) {
      throw new Error('Failed to get sessionId')
    }
    return {
      sessionId: value.slice(12),
      response: aiter(messageStream).map(decodeStreamChunk),
    }
  },

  getSessions(): Promise<{
    status: string
    sessions: Array<{
      sessionId: string
      createdAt: string
      lastActiveAt: string
      conversationRounds: number
      temporary: boolean
    }>
    totalSessions: number
  }> {
    return this.instance.get('/sessions')
  },

  getSessionDetail(id: string): Promise<{
    status: string
    sessionId: string
    messages: Array<{ role: string, content: string }>
    conversationRounds: number
  }> {
    return this.instance.get(`/sessions/${id}`)
  },

  deleteSession(id: string) {
    return this.instance.delete(`/sessions/${id}`)
  },

  clearAllSessions() {
    return this.instance.delete('/sessions')
  },

  getToolStatus(): Promise<{ message: string, visible: boolean }> {
    return this.instance.get('/tool_status')
  },

  getClawdbotReplies(): Promise<{ replies: string[] }> {
    return this.instance.get('/clawdbot/replies')
  },

  uploadDocument(file: File, description?: string): Promise<{
    status: 'success'
    message: string
    filename: string
    filePath: string
    fileSize: number
    fileType: string
    uploadTime: string
  }> {
    const formData = new FormData()
    formData.append('file', file)
    if (description) {
      formData.append('description', description)
    }
    return this.instance.post('/upload/document', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  },

  parseDocument(file: File): Promise<{
    status: 'success'
    filename: string
    content: string
    truncated: boolean
    charCount: number
  }> {
    const formData = new FormData()
    formData.append('file', file)
    return this.instance.post('/upload/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  },
} satisfies DomainShape
