/**
 * 领域包（Domain Pack）前端支持 —— 卷162
 *
 * 职责：
 * 1. 从 `GET /api/domains` 拉取领域包 schema
 * 2. 把领域专属路由动态注册进 vue-router（核心路由在 main.ts 静态声明）
 * 3. 提供当前领域包的响应式状态，供 ElnView 字段渲染 / PanelView 切换器 /
 *    PapersView 来源徽章消费
 *
 * 设计约束（见 domains/law/pack.yaml 与 docs/领域包指南.md）：
 * - 后端不可用时**必须降级**：返回空列表，核心功能不受影响
 * - 不引入新 UI 库
 */

import type { Router } from 'vue-router'
import { computed, ref } from 'vue'

/** ELN 字段 schema（对应 pack.yaml 的 eln.fields[]）。 */
export interface ElnFieldSchema {
  key: string
  type: 'text' | 'textarea' | 'list' | 'date'
  label: string
  required: boolean
  /**
   * 是否进前端表单。后端 frontmatter 生成不受此开关影响（始终含全部字段）。
   * 默认包把 `attachments` 标 false —— 改造前表单就不渲染它。
   */
  show_in_form?: boolean
}

/** 来源预设（对应 pack.yaml 的 source_presets[]）。 */
export interface SourcePreset {
  key: string
  label: string
  license_note: string
}

/** 打标问题（对应 pack.yaml 的 tagging.questions[]，卷164 消费）。 */
export interface TaggingQuestion {
  key: string
  type: 'boolean' | 'choice' | 'score'
  options: string[]
}

/** 单个领域包 schema（对应 GET /api/domains 的 domains[] 元素）。 */
export interface DomainPack {
  name: string
  label: string
  description: string
  eln: { fields: ElnFieldSchema[], form_fields?: ElnFieldSchema[] }
  papers: { id_fields: string[] }
  source_presets: SourcePreset[]
  tagging: { questions: TaggingQuestion[] }
}

export interface DomainsResponse {
  ok: boolean
  default: string
  domains: DomainPack[]
  warnings?: string[]
}

const STORAGE_KEY = 'lumo.domain.active'

/** 全部领域包（后端不可用时为空数组 → 全局降级）。 */
export const domainPacks = ref<DomainPack[]>([])
/** 默认包名（后端返回值，回退 'default'）。 */
export const defaultDomain = ref('default')
/** 当前激活的领域包名。 */
export const activeDomain = ref<string>(
  (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY)) || 'default',
)
/** 加载状态与错误（供设置页展示）。 */
export const domainsLoading = ref(false)
export const domainsError = ref<string>('')

/** 当前领域包对象；找不到时回退到 default，再回退到 undefined。 */
export const currentPack = computed<DomainPack | undefined>(() => {
  const byName = domainPacks.value.find(p => p.name === activeDomain.value)
  if (byName)
    return byName
  return domainPacks.value.find(p => p.name === defaultDomain.value)
})

/**
 * 当前领域包的 ELN **表单**字段 schema（只含 show_in_form 的字段）。
 *
 * 优先消费后端 `eln.form_fields`；后端未提供时本地按 show_in_form 过滤，
 * 保证与后端语义一致。
 */
export const currentElnFields = computed<ElnFieldSchema[]>(() => {
  const eln = currentPack.value?.eln
  if (!eln)
    return []
  if (Array.isArray(eln.form_fields))
    return eln.form_fields
  return (eln.fields ?? []).filter(f => f.show_in_form !== false)
})

/** 当前领域包的全部 ELN 字段（含不进表单的，供只读展示/导出预览）。 */
export const currentAllElnFields = computed<ElnFieldSchema[]>(
  () => currentPack.value?.eln?.fields ?? [],
)

/** 当前领域包的来源预设。 */
export const currentSourcePresets = computed<SourcePreset[]>(
  () => currentPack.value?.source_presets ?? [],
)

/** 切换当前领域包（持久化到 localStorage）。 */
export function setActiveDomain(name: string): void {
  if (!domainPacks.value.some(p => p.name === name)) {
    console.warn(`[domains] 未知领域包: ${name}`)
    return
  }
  activeDomain.value = name
  try {
    localStorage.setItem(STORAGE_KEY, name)
  }
  catch {
    // localStorage 不可用（隐私模式）时忽略，仅内存生效
  }
}

/**
 * 拉取领域包列表。
 *
 * 失败时**不抛异常**，返回空数组并记录错误 —— 这是刻意的降级设计：
 * 领域功能不可用不应影响核心功能。
 */
export async function fetchDomainPacks(): Promise<DomainPack[]> {
  domainsLoading.value = true
  domainsError.value = ''
  try {
    const resp = await fetch('/api/domains', {
      headers: { Accept: 'application/json' },
    })
    if (!resp.ok)
      throw new Error(`HTTP ${resp.status}`)
    const data = (await resp.json()) as DomainsResponse
    if (!data || !Array.isArray(data.domains))
      throw new Error('响应缺少 domains 数组')

    domainPacks.value = data.domains
    defaultDomain.value = data.default || 'default'
    if (data.warnings?.length)
      console.warn('[domains] 后端告警:', data.warnings)

    // 激活名失效时回退默认包
    if (!data.domains.some(p => p.name === activeDomain.value))
      activeDomain.value = defaultDomain.value

    return data.domains
  }
  catch (err) {
    domainsError.value = err instanceof Error ? err.message : String(err)
    domainPacks.value = []
    console.warn('[domains] 领域包加载失败，领域功能降级:', err)
    return []
  }
  finally {
    domainsLoading.value = false
  }
}

/**
 * 领域专属视图的懒加载映射。
 *
 * 约定：领域视图放 `src/views/domains/<name>/IndexView.vue`。用
 * `import.meta.glob` 做静态可分析收集 —— 相比模板字符串动态 import，
 * 它在目录为空时也不会导致构建失败，且完全由 Vite 静态分析（无运行时
 * 路径拼接），新增领域只需放文件，无需改此文件。
 */
const domainViews = import.meta.glob('../views/domains/*/IndexView.vue') as Record<
  string,
  () => Promise<unknown>
>

/** 按包名取对应的领域视图组件；无对应文件时返回 undefined。 */
function resolveDomainView(name: string): (() => Promise<unknown>) | undefined {
  const key = `../views/domains/${name}/IndexView.vue`
  return domainViews[key]
}

/**
 * 把领域专属路由注册进 router。
 *
 * 领域视图按约定命名：`src/views/domains/<name>/IndexView.vue`，路径 `/<name>`。
 * 对应的视图文件缺失时跳过该领域（不抛异常），避免一个包缺文件导致整个应用
 * 启动失败 —— 领域包可以只提供配置而暂不提供独立视图。
 */
export async function registerDomainRoutes(router: Router): Promise<void> {
  const packs = await fetchDomainPacks()
  for (const pack of packs) {
    // default 包复用现有核心路由（/eln 等），不额外注册
    if (pack.name === defaultDomain.value)
      continue

    const routeName = `domain-${pack.name}`
    if (router.hasRoute(routeName))
      continue

    const view = resolveDomainView(pack.name)
    if (!view) {
      console.warn(`[domains] 领域 ${pack.name} 无专属视图（views/domains/${pack.name}/IndexView.vue），跳过路由注册`)
      continue
    }

    router.addRoute({
      path: `/${pack.name}`,
      name: routeName,
      component: view,
      meta: { domain: pack.name, domainLabel: pack.label },
    })
  }
}
