/**
 * api 层共享类型（卷191-A2 从 core.ts 拆出）。
 * 原样搬运，字段与注释零改动。
 */

export interface OpenClawStatus {
  found: boolean
  version?: string
  skills_dir: string
  config_path: string
  skills_error?: string
}

export interface CharacterTemplate {
  name: string
  aiName?: string
  bio?: string
  voice?: string
  promptFile?: string
  portrait?: string
  live2dModel?: string
  live2dModelUrl?: string
  active?: boolean
}

export interface CustomLive2DModel {
  id: string
  name: string
  modelPath: string
  source: string
  fileCount: number
  totalBytes: number
  createdAt: string
}

export type AgentEngine = 'openclaw' | 'lumo-core' | 'naga-core'

export interface SkillCatalogItem {
  name: string
  description: string
  version?: string
  tags?: string[]
  scope: 'cache' | 'public' | 'private'
  source: string
  path: string
  ownerAgentId?: string
  ownerAgentName?: string
  ownerEngine?: AgentEngine
}

export interface SkillCatalogSection {
  skills: SkillCatalogItem[]
  baseDir?: string
  baseDirs?: string[]
}

export interface AgentSettings {
  id: string
  name: string
  engine: AgentEngine
  characterTemplate?: string
  soulContent?: string
}

export interface McpService {
  name: string
  displayName: string
  description: string
  source: 'builtin' | 'mcporter'
  scope: 'public' | 'private'
  ownerAgentId?: string | null
  ownerAgentName?: string | null
  available: boolean
  enabled: boolean
  disabledReason?: string | null
  /**
   * 内置 agent 的依赖预检（requires）；mcporter 外部服务无此字段。
   *  missing=必须依赖缺失；optional_missing=软依赖缺失（功能降级但可用）
   */
  requirements?: { declared: boolean, missing: string[], optional_missing?: string[] }
  config?: Record<string, any>
}

export interface ToolStats {
  calls: number
  p50_ms: number
  p95_ms: number
  errors: number
  error_rate: number
  last_error: string
  last_call_ts: number
}

export interface ToolCircuitState {
  tool: string
  state: 'closed' | 'open' | 'half_open'
  samples: number
  failures: number
  fail_rate: number
  open_until: number
  last_error: string
}

export interface MarketItem {
  id: string
  title: string
  description: string
  skill_name?: string
  enabled: boolean
  installed: boolean
  eligible?: boolean
  disabled?: boolean
  missing?: boolean
  skill_path: string
  openclaw_visible: boolean
  install_type: string
}

export interface MemoryStats {
  totalQuintuples: number
  contextLength: number
  cacheSize: number
  activeTasks: number
  taskManager: {
    enabled: boolean
    totalTasks: number
    pendingTasks: number
    runningTasks: number
    completedTasks: number
    failedTasks: number
    cancelledTasks: number
    maxWorkers: number
    maxQueueSize: number
    queueSize: number
    queueUsage: string
    taskTimeout: number
  }
}

export interface Quintuple {
  subject: string
  subjectType: string
  predicate: string
  object: string
  objectType: string
  /** with_degree=true 时后端回填的实体连接数 */
  degree?: number
}

export interface QuintuplePage {
  status: string
  quintuples: Quintuple[]
  count: number
  total?: number
  offset?: number
  limit?: number
  has_more?: boolean
}

export interface GraphSummary {
  status: string
  total_quintuples: number
  total_entities: number
  top_entities: Array<{ id: string, type: string, degree: number }>
  subject_types: Array<{ type: string, count: number }>
  object_types: Array<{ type: string, count: number }>
  predicate_distribution: Array<{ predicate: string, count: number }>
}

export interface Paper {
  id: number
  title: string
  doi?: string | null
  authors?: string[]
  journal?: string | null
  year?: number | null
  tags?: string[]
  notes?: string | null
  abstract?: string | null
  mdPath?: string | null
  linkedExperiments?: string[]
  createdAt?: string
  // 卷163：来源标注（pkulaw / wkinfo / flk / manual …）与版权说明
  // 注意：后端 papers 接口按 snake_case 返回（见 _row_to_dict）。
  source?: string | null
  license_note?: string | null
  // 卷162：领域包主键（law 包为 flk_id / case_no）
  flk_id?: string | null
  case_no?: string | null
  // 卷164：AI 打标置信明细（JSON 字符串，见 papers.tag_confidence）
  tag_confidence?: string | null
}

export interface TagResult {
  value: string | boolean | number
  confidence: number
  probs: Record<string, number>
  source: 'von' | '人工'
  accepted: boolean
}

export interface TagConfidence {
  questions: Record<string, TagResult>
  low_confidence: Record<string, TagResult>
  threshold: number
  context_chars: number
  truncated: boolean
  tagged_at: string
}

export interface VonStatus {
  success: boolean
  enabled: boolean
  alive: boolean
  endpoint: string
  breaker: 'closed' | 'open' | 'half_open'
  message: string
}

export interface ElnRecord {
  id: string
  date: string
  topic: string
  status: string
  purpose: string
  reagents: string
  conditions: string
  results: string
  attachments: string[]
  conclusion: string
  references: string
  /**
   * 领域包扩展字段（卷162）。default 包不产生额外键；law 包会带
   * parties / cause_of_action / dispute_focus / holding / legal_basis /
   * related_cases 等。索引签名为宽类型，避免为每个领域改动本接口。
   */
  [key: string]: any
}

export type ElnRecordInput = Omit<ElnRecord, 'id'>
