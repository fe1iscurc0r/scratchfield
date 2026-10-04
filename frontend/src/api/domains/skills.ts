import type { DomainShape } from './_context'
/**
 * skills 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { McpService, SkillCatalogSection, ToolCircuitState, ToolStats } from './_types'

export const skillsMethods = {
  getMcpStatus(): Promise<{
    server: string
    timestamp: string
    tasks: { total: number, active: number, completed: number, failed: number }
    scheduler?: Record<string, any>
  }> {
    return this.instance.get('/mcp/status')
  },

  getMcpServices(): Promise<{
    status: string
    services: McpService[]
  }> {
    return this.instance.get('/mcp/services', {
      params: { _t: Date.now() },
    })
  },

  getMcpAssembly(): Promise<{
    policy: Record<string, any>
    vocabulary: {
      families: { key: string, label: string, desc: string }[]
      tiers: { key: string, label: string, desc: string }[]
    }
    agents: { name: string, enabled: boolean, disabled_reason?: string }[]
  }> {
    return this.instance.get('/mcp/assembly', { params: { _t: Date.now() } })
  },

  getToolStats(window = '7d'): Promise<{
    window: string
    stats: Record<string, ToolStats>
  }> {
    return this.instance.get('/tools/stats', { params: { window, _t: Date.now() } })
  },

  getToolCircuit(): Promise<{ circuits: Record<string, ToolCircuitState> }> {
    return this.instance.get('/tools/circuit', { params: { _t: Date.now() } })
  },

  updateMcpAssembly(body: {
    enabled_families?: string[] | null
    disable_tiers?: string[] | null
    disabled_agents?: string[] | null
  }): Promise<{
    status: string
    message: string
    updated: string[]
  }> {
    return this.instance.put('/mcp/assembly', body)
  },

  importMcpConfig(params: {
    name: string
    config: Record<string, any>
    displayName?: string
    description?: string
    scope?: 'public' | 'private'
    agentId?: string
  }): Promise<{
    status: string
    message: string
  }> {
    return this.instance.post('/mcp/import', params)
  },

  updateMcpService(name: string, body: Record<string, any>): Promise<{
    status: string
    message: string
  }> {
    return this.instance.put(`/mcp/services/${encodeURIComponent(name)}`, body)
  },

  deleteMcpService(name: string): Promise<{
    status: string
    message: string
  }> {
    return this.instance.delete(`/mcp/services/${encodeURIComponent(name)}`)
  },

  importCustomSkill(name: string, content: string): Promise<{
    status: string
    message: string
  }> {
    return this.instance.post('/skills/import', { name, content })
  },

  getSkillCatalog(): Promise<{
    status: 'success'
    catalog: {
      remoteHub: {
        status: string
        message: string
        baseUrl?: string
        skillEndpointTemplate?: string
        mcpEndpointTemplate?: string
      }
      localCache: SkillCatalogSection
      publicSkills: SkillCatalogSection
      privateSkills: SkillCatalogSection
    }
  }> {
    return this.instance.get('/skills/catalog')
  },

  importScopedSkill(params: {
    name: string
    content: string
    scope: 'cache' | 'public' | 'private'
    agentId?: string
  }): Promise<{
    status: string
    message: string
    scope: string
    path: string
  }> {
    return this.instance.post('/skills/import', params)
  },

  cloneSkill(params: {
    name: string
    sourceScope: 'cache' | 'public' | 'private'
    targetScope: 'cache' | 'public' | 'private'
    sourceAgentId?: string
    targetAgentId?: string
  }): Promise<{
    status: string
    message: string
    sourceScope: string
    targetScope: string
    path: string
  }> {
    return this.instance.post('/skills/clone', params)
  },

  deleteSkill(name: string, scope: 'cache' | 'public' | 'private', agentId?: string): Promise<{
    status: string
    message: string
    scope: string
    path: string
  }> {
    return this.instance.delete(`/skills/${encodeURIComponent(name)}`, {
      params: {
        scope,
        agent_id: agentId,
      },
    })
  },

  installHubSkill(params: {
    name: string
    scope: 'cache' | 'public' | 'private'
    agentId?: string
    source?: string
  }): Promise<{
    status: string
    message: string
    scope: string
    path: string
    name: string
    source: string
  }> {
    return this.instance.post('/hub/skills/install', params)
  },

  installHubMcp(params: {
    name: string
    scope: 'public' | 'private'
    agentId?: string
    source?: string
  }): Promise<{
    status: string
    message: string
    scope: string
    name: string
    source: string
  }> {
    return this.instance.post('/hub/mcp/install', params)
  },

  getOpenclawTasks(): Promise<{
    status: string
    tasks: Array<Record<string, any>>
  }> {
    return this.instance.get('/openclaw/tasks')
  },

  getOpenclawTaskDetail(taskId: string): Promise<Record<string, any>> {
    return this.instance.get(`/openclaw/tasks/${taskId}`)
  },

  getMcpTasks(status?: string): Promise<Record<string, any>> {
    const params = status ? `?status=${status}` : ''
    return this.instance.get(`/mcp/tasks${params}`)
  },
} satisfies DomainShape
