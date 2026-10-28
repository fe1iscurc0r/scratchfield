export interface TravelDiscovery {
  url: string
  title: string
  summary: string
  foundAt: string
  tags: string[]
}

export interface SocialInteraction {
  type: string
  postId?: string
  contentPreview: string
  timestamp: string
}

export interface TravelProgressEvent {
  timestamp: string
  type: string
  message: string
  level?: 'info' | 'warn' | 'error'
  meta?: Record<string, unknown>
}

export interface TravelSession {
  sessionId: string
  status: 'pending' | 'running' | 'interrupted' | 'completed' | 'failed' | 'cancelled'
  phase?: string
  createdAt: string
  phaseStartedAt?: string
  lastCheckpointAt?: string
  startedAt?: string
  completedAt?: string
  interruptedAt?: string
  interruptedReason?: string
  agentId?: string
  agentName?: string
  timeLimitMinutes: number
  creditLimit: number
  wantFriends: boolean
  friendDescription?: string
  goalPrompt?: string
  // postToForum 已移除：论坛下线后该开关在后端不被任何逻辑读取（纯惰性管道），
  // 全仓也没有任何调用方设置它，保留只会让人以为「探索能发帖」。
  deliverFullReport?: boolean
  deliverChannel?: string
  deliverTo?: string
  browserVisible?: boolean
  browserKeepOpen?: boolean
  browserIdleTimeoutSeconds?: number
  openclawSessionKey?: string
  lastHeartbeatAt?: string
  resumeCount?: number
  tokensUsed: number
  creditsUsed: number
  elapsedMinutes: number
  toolStats?: Record<string, number>
  uniqueSources?: number
  sources?: string[]
  summaryReportPath?: string
  summaryReportTitle?: string
  wrapUpSent?: boolean
  idlePolls?: number
  progressEvents?: TravelProgressEvent[]
  discoveries: TravelDiscovery[]
  socialInteractions: SocialInteraction[]
  summary?: string
  // forumDigest / forumPostId / forumPostStatus 已移除：三者恒为 null
  // （后端从未给它们赋值），前端也没有任何读取方。
  fullReportDeliveryStatus?: string
  notificationDeliveryStatuses?: Record<string, string>
  error?: string
}
