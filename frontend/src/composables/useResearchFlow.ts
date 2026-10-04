/**
 * 科研工作流上下文（卷147）
 *
 * 四件套（文献 → 实验 → 数据 → 模型/报告）之间的 payload 传递载体。
 *
 * 为什么用 provide/inject 而不是 pinia：本仓库未引入 pinia（package.json 无该依赖），
 * 按工单"选轻的"要求，用 Vue 原生 provide/inject + 模块级响应式对象实现，
 * 零新增依赖（供应链铁律：能不加包就不加）。
 *
 * 生命周期：ResearchFlowBar 组件 provide 该上下文；各视图通过 useResearchFlow() 消费。
 * 跨视图跳转时 payload 存在模块级 ref 中（比内存会话稍长，刷新页面即清空 —— 符合
 * "临时上下文"语义，不应持久化到 localStorage）。
 */
import type { InjectionKey, Ref } from 'vue'
import { inject, ref } from 'vue'

export type FlowStep = 'papers' | 'eln' | 'data' | 'model'

export interface FlowContext {
  /** 当前活跃步骤 */
  step: Ref<FlowStep>
  /** 待在建 ELN 记录中预填的引用文献（Papers → ELN） */
  pendingCitation: Ref<string>
  /** 待挂到该 ELN 记录的数据图附件（Data → ELN） */
  pendingAttachment: Ref<string>
  /** 当前聚焦的 ELN 记录 id（ELN → 模型预测） */
  focusedRecordId: Ref<string>
  /** 设置引用文献并跳到 ELN */
  citeToEln: (citation: string, paperId?: number) => void
  /** 把数据图附到指定 ELN 记录 */
  attachToEln: (recordId: string, attachment: string) => void
  /** 记录来源文献 id（用于回写 papers.linked_experiments） */
  sourcePaperId: Ref<number | null>
}

export const RESEARCH_FLOW_KEY: InjectionKey<FlowContext> = Symbol('research-flow')

/** 模块级单例状态：跨视图跳转时 payload 得以延续（组件重挂载不丢） */
const step = ref<FlowStep>('papers')
const pendingCitation = ref('')
const pendingAttachment = ref('')
const focusedRecordId = ref('')
const sourcePaperId = ref<number | null>(null)

const ctx: FlowContext = {
  step,
  pendingCitation,
  pendingAttachment,
  focusedRecordId,
  sourcePaperId,
  citeToEln(citation: string, paperId?: number) {
    pendingCitation.value = citation
    sourcePaperId.value = paperId ?? null
    step.value = 'eln'
  },
  attachToEln(recordId: string, attachment: string) {
    focusedRecordId.value = recordId
    pendingAttachment.value = attachment
    step.value = 'eln'
  },
}

/** 供 ResearchFlowBar provide 用（返回同一个单例，保证多视图共享） */
export function createResearchFlow(): FlowContext {
  return ctx
}

/** 视图侧消费入口。未包在 ResearchFlowBar 内时返回 null，调用方需容错。 */
export function useResearchFlow(): FlowContext | null {
  return inject(RESEARCH_FLOW_KEY, null)
}

/** 清空临时 payload（视图消费后调用，避免重复预填） */
export function clearPending() {
  pendingCitation.value = ''
  pendingAttachment.value = ''
}
