/**
 * agents 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { AgentEngine, AgentSettings } from './_types'
import { agentAxios } from './_internals'

/** 同域跨方法调用所需的自身方法签名（仅用于 this 类型） */
interface AgentsSelfRef {
  streamToAgent: (id: string, message: string, timeoutSeconds?: number) => AsyncGenerator<{ type: string, text: string }>
  getAgentHistory: (id: string, limit?: number) => Promise<{ messages: Array<{ role: string, content: string }> }>
}

type AgentsShape
  = & Record<string, (...args: any[]) => any>
    & ThisType<import('./_context').DomainContext & AgentsSelfRef>

export const agentsMethods = {
  listAgents(): Promise<{ agents: Array<{ id: string, name: string, running: boolean, createdAt?: number, created_at?: number, characterTemplate?: string, engine?: AgentEngine }> }> {
    return agentAxios.get('/openclaw/agents')
  },

  createAgent(name?: string, characterTemplate?: string, engine: AgentEngine = 'openclaw'): Promise<{ id: string, name: string, running: boolean, characterTemplate?: string, engine?: AgentEngine }> {
    return agentAxios.post('/openclaw/agents', { name, characterTemplate, engine })
  },

  deleteAgent(id: string, deleteData = true): Promise<{ success: boolean }> {
    return agentAxios.delete(`/openclaw/agents/${id}?delete_data=${deleteData}`)
  },

  renameAgent(id: string, name: string): Promise<{ success: boolean, name: string }> {
    return agentAxios.put(`/openclaw/agents/${id}/name`, { name })
  },

  getAgentRuntime(id: string, wake = false): Promise<{
    success: boolean
    runtime: {
      id: string
      name: string
      engine: AgentEngine
      running: boolean
      woken?: boolean
      port?: number | null
      gatewayUrl?: string | null
      primary?: boolean
    }
  }> {
    return agentAxios.get(`/openclaw/agents/${id}/runtime`, { params: { wake } })
  },

  getAgentHistory(id: string, limit = 50): Promise<{ messages: Array<{ role: string, content: string, toolEvents?: any[] }> }> {
    return agentAxios.get(`/openclaw/agents/${id}/history`, { params: { limit } })
  },

  getAgentSettings(id: string): Promise<AgentSettings> {
    return agentAxios.get(`/openclaw/agents/${id}/settings`)
  },

  updateAgentSettings(id: string, body: {
    name?: string
    engine?: AgentEngine
    characterTemplate?: string
    soulContent?: string
  }): Promise<AgentSettings> {
    return agentAxios.put(`/openclaw/agents/${id}/settings`, body)
  },

  relayAgentMessage(params: {
    message: string
    targetAgentId?: string
    targetAgentName?: string
    sourceAgentId?: string
    sourceAgentName?: string
    purpose?: string
    context?: string
    timeoutSeconds?: number
    sessionId?: string
  }): Promise<{
    success: boolean
    status: string
    reply?: string
    error?: string
    session_id?: string
    session_key?: string
    target?: { id: string, name: string, engine: string, character_template?: string, builtin?: boolean }
  }> {
    return this.instance.post('/agents/relay', {
      message: params.message,
      target_agent_id: params.targetAgentId,
      target_agent_name: params.targetAgentName,
      source_agent_id: params.sourceAgentId,
      source_agent_name: params.sourceAgentName,
      purpose: params.purpose,
      context: params.context,
      timeout_seconds: params.timeoutSeconds,
      session_id: params.sessionId,
    })
  },

  async* streamToAgent(id: string, message: string, timeoutSeconds = 120): AsyncGenerator<{
    type: string
    text: string
    name?: string
    toolCallId?: string
    args?: any
    result?: any
    isError?: boolean
  }> {
    const resp = await fetch(`http://localhost:8001/openclaw/agents/${id}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify({ message, timeout_seconds: timeoutSeconds }),
    })

    if (!resp.ok || !resp.body)
      throw new Error(`Stream failed: ${resp.status}`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done)
        break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            yield JSON.parse(line.slice(6))
          }
          catch { /* skip malformed */ }
        }
      }
    }
  },

  createAgentInstance(name?: string): Promise<{ id: string, name: string, port: number, primary: boolean }> {
    return agentAxios.post('/openclaw/instances', { name })
  },

  destroyAgentInstance(id: string): Promise<{ success: boolean }> {
    return agentAxios.delete(`/openclaw/instances/${id}`)
  },

  listAgentInstances(): Promise<{ instances: Array<{ id: string, name: string, port: number, primary: boolean }> }> {
    return agentAxios.get('/openclaw/instances')
  },

  sendToAgentInstance(id: string, message: string, timeoutSeconds = 120): Promise<{ success: boolean, reply?: string, replies?: string[], error?: string, retry?: boolean }> {
    return agentAxios.post(`/openclaw/instances/${id}/send`, {
      message,
      timeout_seconds: timeoutSeconds,
    })
  },

  async* streamToAgentInstance(id: string, message: string, timeoutSeconds = 120): AsyncGenerator<{ type: string, text: string }> {
    yield* this.streamToAgent(id, message, timeoutSeconds)
  },

  renameAgentInstance(id: string, name: string): Promise<{ success: boolean, name: string }> {
    return agentAxios.put(`/openclaw/agents/${id}/name`, { name })
  },

  getAgentInstanceHistory(id: string, limit = 50): Promise<{ messages: Array<{ role: string, content: string }> }> {
    return this.getAgentHistory(id, limit)
  },
} satisfies AgentsShape
