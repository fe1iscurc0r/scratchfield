import type { DomainShape } from './_context'
/**
 * travel 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 *
 * `postToForum` 参数已移除（2026-10-12）：论坛下线后后端不读它、全仓无人设置它，
 * 留在签名里等于对外承诺一个不存在的功能。详见 docs/travel-exploration-system.md。
 */
import type { TravelSession } from './_internals'

export const travelMethods = {
  startTravel(params: {
    agentId?: string
    timeLimitMinutes?: number
    creditLimit?: number
    wantFriends?: boolean
    friendDescription?: string
    goalPrompt?: string
    deliverFullReport?: boolean
    deliverChannel?: string
    deliverTo?: string
    browserVisible?: boolean
    browserKeepOpen?: boolean
    browserIdleTimeoutSeconds?: number
  }): Promise<{ status: 'success', sessionId: string }> {
    return this.instance.post('/travel/start', params)
  },

  createTravelSession(params: {
    agentId?: string
    timeLimitMinutes?: number
    creditLimit?: number
    wantFriends?: boolean
    friendDescription?: string
    goalPrompt?: string
    deliverFullReport?: boolean
    deliverChannel?: string
    deliverTo?: string
    browserVisible?: boolean
    browserKeepOpen?: boolean
    browserIdleTimeoutSeconds?: number
  }): Promise<{ status: 'success', sessionId: string, session: TravelSession }> {
    return this.instance.post('/travel/sessions', params)
  },

  updateTravelSessionBrowser(sessionId: string, params: {
    browserVisible?: boolean
    browserKeepOpen?: boolean
    browserIdleTimeoutSeconds?: number
  }): Promise<{ status: 'success', session: TravelSession }> {
    return this.instance.post(`/travel/sessions/${sessionId}/browser`, params)
  },

  sendTravelInstruction(sessionId: string, message: string): Promise<{ status: 'success', session: TravelSession }> {
    return this.instance.post(`/travel/sessions/${sessionId}/instruction`, { message })
  },

  getTravelStatus(): Promise<{
    status: 'success'
    session: TravelSession | null
    active: boolean
  }> {
    return this.instance.get('/travel/status')
  },

  getTravelSessions(): Promise<{
    status: 'success'
    sessions: TravelSession[]
  }> {
    return this.instance.get('/travel/sessions')
  },

  getTravelSession(sessionId: string): Promise<{
    status: 'success'
    session: TravelSession
  }> {
    return this.instance.get(`/travel/sessions/${sessionId}`)
  },

  getTravelSessionReport(sessionId: string): Promise<{
    status: 'success'
    exists: boolean
    path: string | null
    title?: string | null
    content: string | null
    missingReason?: 'not_generated' | 'missing'
  }> {
    return this.instance.get(`/travel/sessions/${sessionId}/report`)
  },

  getTravelSessionHistory(sessionId: string, limit = 0, includeTools = true): Promise<{
    status: 'success'
    sessionId: string
    sessionKey: string | null
    messages: Array<Record<string, any>>
  }> {
    return this.instance.get(`/travel/sessions/${sessionId}/history`, {
      params: {
        limit,
        include_tools: includeTools,
      },
    })
  },

  stopTravel(sessionId?: string): Promise<{ status: 'success', sessionId: string }> {
    return this.instance.post('/travel/stop', sessionId ? { sessionId } : {})
  },

  stopTravelSession(sessionId: string): Promise<{ status: 'success', sessionId: string, session: TravelSession }> {
    return this.instance.post(`/travel/sessions/${sessionId}/stop`)
  },

  getTravelHistory(): Promise<{
    status: 'success'
    sessions: TravelSession[]
  }> {
    return this.instance.get('/travel/history')
  },
} satisfies DomainShape
