import { agentsMethods } from './domains/agents'
import { appsMethods } from './domains/apps'
import { authMethods } from './domains/auth'
import { chatMethods } from './domains/chat'
import { dataToolsMethods } from './domains/dataTools'
import { sentinelMethods } from './domains/sentinel'
import { elnMethods } from './domains/eln'
import { lawMethods } from './domains/law'
import { marketMethods } from './domains/market'
import { mediaMethods } from './domains/media'
import { memoryMethods } from './domains/memory'
import { papersMethods } from './domains/papers'
import { skillsMethods } from './domains/skills'
import { systemMethods } from './domains/system'
import { travelMethods } from './domains/travel'
/**
 * api/core.ts —— 薄壳（卷191-A2 拆域后）。
 *
 * 原 1617 行巨石按后端域拆到 ./domains/ 下。本文件只做三件事：
 *   1. re-export 全部类型（存量 `import type { X } from '@/api/core'` 零改动）
 *   2. 定义 CoreApiClient（继承 ApiClient），把各域方法装到原型上
 *   3. 导出单例（default）
 *
 * 兼容红线：函数签名、返回类型、default 实例的行为与拆分前完全一致。
 */
import { ApiClient } from './index'

export type {
  AgentEngine,
  AgentSettings,
  CharacterTemplate,
  CustomLive2DModel,
  ElnRecord,
  ElnRecordInput,
  GraphSummary,
  MarketItem,
  McpService,
  MemoryStats,
  OpenClawStatus,
  Paper,
  Quintuple,
  QuintuplePage,
  SkillCatalogItem,
  SkillCatalogSection,
  TagConfidence,
  TagResult,
  ToolCircuitState,
  ToolStats,
  VonStatus,
} from './domains/_types'

// 原样保留：core.ts 历史上转发旅行类型
export type { SocialInteraction, TravelDiscovery, TravelSession } from '@/travel/types'

/** 各域方法集合（装到 CoreApiClient 原型上） */
const domains = {
  ...systemMethods,
  ...chatMethods,
  ...memoryMethods,
  ...skillsMethods,
  ...mediaMethods,
  ...authMethods,
  ...travelMethods,
  ...marketMethods,
  ...agentsMethods,
  ...papersMethods,
  ...lawMethods,
  ...elnMethods,
  ...appsMethods,
  ...dataToolsMethods,
  ...sentinelMethods,
}

/** 合并后的方法类型（供实例类型使用） */
export type CoreApiDomains = typeof domains

export class CoreApiClient extends ApiClient {}

Object.assign(CoreApiClient.prototype, domains)

/** 带全部域方法的实例类型 */
export type CoreApi = CoreApiClient & CoreApiDomains

export default new CoreApiClient(8000) as CoreApi
