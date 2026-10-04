import type { DomainShape } from './_context'
import type { Config } from './_internals'
/**
 * system 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { CharacterTemplate, CustomLive2DModel } from './_types'
import { agentAxios } from './_internals'

export const systemMethods = {
  getActiveCharacter(): Promise<{
    status: string
    character: {
      name: string
      ai_name: string
      user_name?: string
      prompt_file?: string
      live2d_model_url?: string
    }
  }> {
    return this.instance.get('/system/character')
  },

  health(): Promise<{
    status: 'healthy'
    agentReady: true
    timestamp: string
  }> {
    // 添加时间戳防止 Chromium HTTP 缓存返回旧响应（快速重启场景）
    return this.instance.get(`/health?_t=${Date.now()}`)
  },

  agentServerHealth(): Promise<Record<string, any>> {
    return agentAxios.get(`/health?_t=${Date.now()}`)
  },

  agentServerFullHealth(): Promise<Record<string, any>> {
    return agentAxios.get(`/health/full?_t=${Date.now()}`)
  },

  agentServerOpenclawHealth(): Promise<Record<string, any>> {
    return agentAxios.get(`/openclaw/health?_t=${Date.now()}`)
  },

  systemInfo(): Promise<{
    version: string
    status: 'running'
    availableServices: []
    apiKeyConfigured: boolean
  }> {
    return this.instance.get('/system/info')
  },

  systemConfig(): Promise<{
    status: 'success'
    config: Config
  }> {
    // 配置对象使用 snake_case 键名，跳过自动 camelCase 转换以避免键名不匹配
    // 添加时间戳防止 HTTP 缓存（快速重启场景）
    return this.instance(`/system/config?_t=${Date.now()}`, {
      transformResponse: [(data: string) => JSON.parse(data)],
    })
  },

  setSystemConfig(config: Config): Promise<{
    status: 'success'
    message: string
  }> {
    // 配置对象已是 snake_case，跳过自动 snakeCase 转换避免双重处理
    return this.instance.post('/system/config', config, {
      transformRequest: [(data: unknown) => JSON.stringify(data)],
      transformResponse: [(data: string) => JSON.parse(data)],
    })
  },

  openclawGatewayStatus(): Promise<{
    success: boolean
    running: boolean
    enabled: boolean
    port: number
    port_in_use: boolean
  }> {
    return this.instance.get('/openclaw/gateway/status')
  },

  openclawGatewayStart(): Promise<{
    success: boolean
    running: boolean
    message: string
  }> {
    return this.instance.post('/openclaw/gateway/start', {}, { timeout: 60 * 1000 })
  },

  openclawGatewayStop(): Promise<{
    success: boolean
    running: boolean
    message: string
  }> {
    return this.instance.post('/openclaw/gateway/stop', {}, { timeout: 30 * 1000 })
  },

  trackTelemetry(params: {
    event: string
    props?: Record<string, any>
    source?: string
    traceId?: string
    sessionId?: string
    agentId?: string
  }): Promise<{ status: 'accepted' }> {
    return this.instance.post('/telemetry/track', params)
  },

  flushTelemetry(): Promise<{
    status: 'ok'
    result: Record<string, any>
  }> {
    return this.instance.post('/telemetry/flush')
  },

  getTelemetryStatus(): Promise<{
    status: 'success'
    telemetry: Record<string, any>
  }> {
    return this.instance.get('/telemetry/status')
  },

  getSystemPrompt(): Promise<{
    status: 'success'
    prompt: string
  }> {
    return this.instance.get('/system/prompt')
  },

  setSystemPrompt(content: string): Promise<{
    status: 'success'
    message: string
  }> {
    return this.instance.post('/system/prompt', { content })
  },

  listCharacterTemplates(): Promise<{
    status: 'success'
    activeCharacter?: string
    characters: CharacterTemplate[]
  }> {
    return this.instance.get('/system/characters')
  },

  listCustomLive2DModels(): Promise<{
    status: 'success'
    models: CustomLive2DModel[]
  }> {
    return this.instance.get('/system/live2d/custom-models')
  },

  uploadCustomLive2DModel(params: {
    name: string
    files: File[]
    modelPath?: string
  }): Promise<{
    status: 'success'
    model: CustomLive2DModel
  }> {
    const formData = new FormData()
    formData.append('name', params.name)
    if (params.modelPath) {
      formData.append('model_path', params.modelPath)
    }
    for (const file of params.files) {
      const relativePath = file.webkitRelativePath || file.name
      formData.append('files', file, relativePath)
    }
    return this.instance.post('/system/live2d/custom-models', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },

  deleteCustomLive2DModel(id: string): Promise<{
    status: 'success'
    message: string
  }> {
    return this.instance.delete(`/system/live2d/custom-models/${encodeURIComponent(id)}`)
  },
} satisfies DomainShape
