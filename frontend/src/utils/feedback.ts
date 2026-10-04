/**
 * 统一反馈 API（卷150 任务D）——三级反馈，视图层不再直接 toast.add。
 *
 * 语义（工单原文）：
 *   success(行内)  → 成功操作改行内状态徽章，不打扰
 *   warn(toast)    → 需要用户注意的警告
 *   error(toast+详情) → 失败必须可见，可展开详情
 *
 * 对接约定：
 *   import { feedback } from '@/utils/feedback'
 *   feedback.success('已保存')            // 行内徽章（默认目标 = 当前激活元素旁）
 *   feedback.warn('配置未保存，重启后失效')
 *   feedback.error('导入失败', 'DOI 解析超时：10.xxxx/xxxx')
 *
 * 实现说明：
 *   - toast 部分桥接 PrimeVue ToastService（App 挂载过 .use(ToastService)），
 *     懒加载 useToast —— 在组件外调用（如 store/工具函数）也安全。
 *   - success 行内徽章：向 trigger 元素注入一个短暂的 <span>，
 *     避免为「已保存✓」这种一闪而过的反馈弹全局 toast。
 *   - 纯逻辑部分（shouldToast / level 判定）独立导出，node:test 可测。
 */
import type { ToastServiceMethods } from 'primevue/toastservice'

export type FeedbackLevel = 'success' | 'warn' | 'error'

/** 反馈等级 → 是否走全局 toast（success 不走） */
export function shouldToast(level: FeedbackLevel): boolean {
  return level !== 'success'
}

/** toast severity 映射（PrimeVue 语义） */
export function toastSeverity(level: FeedbackLevel): 'warn' | 'error' {
  return level === 'error' ? 'error' : 'warn'
}

/** 行内徽章存活时长（ms） */
export const INLINE_BADGE_MS = 1600

let toastMethods: ToastServiceMethods | null = null

/** 桥接点：App.vue onMounted 时注入一次（懒连接，避免循环依赖） */
export function bindToast(methods: ToastServiceMethods): void {
  toastMethods = methods
}

function showToast(level: FeedbackLevel, summary: string, detail?: string) {
  if (!toastMethods) {
    // 兜底：未绑定时退化为 console（不静默吞掉）
    console.warn(`[feedback:${level}]`, summary, detail ?? '')
    return
  }
  toastMethods.add({
    severity: toastSeverity(level),
    summary,
    detail: detail || undefined,
    life: level === 'error' ? 7000 : 4000,
  })
}

/** 在触发元素旁渲染行内「✓ summary」徽章（detail 落到悬停提示，不额外打扰） */
function showInlineBadge(summary: string, detail?: string) {
  const host = document.activeElement as HTMLElement | null
  const anchor = host?.closest('button, .p-button, [role="button"], .inline-feedback-anchor') as HTMLElement | null
  if (!anchor || !anchor.parentElement) {
    // 找不到锚点：降级为 toast 吗？不——降级会违背"success 不打扰"语义，
    // 静默跳过并留 console 痕迹
    console.info('[feedback:success]', summary, detail ?? '')
    return
  }
  const badge = document.createElement('span')
  badge.className = 'lumo-inline-feedback'
  badge.textContent = `✓ ${summary}`
  if (detail)
    badge.title = detail
  anchor.insertAdjacentElement('afterend', badge)
  setTimeout(() => badge.remove(), INLINE_BADGE_MS)
}

export const feedback = {
  /** 成功：行内徽章（不打扰）；detail 可选，落到徽章悬停提示 */
  success(summary: string, detail?: string): void {
    showInlineBadge(summary, detail)
  },

  /** 警告：全局 toast */
  warn(summary: string, detail?: string): void {
    showToast('warn', summary, detail)
  },

  /** 失败：全局 toast + 可展开详情 */
  error(summary: string, detail?: string): void {
    showToast('error', summary, detail)
  },
}
