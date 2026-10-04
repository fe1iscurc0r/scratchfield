/**
 * 全局快捷键层（卷150 任务C）——配置表驱动，单一注册点。
 *
 * 对接约定：App.vue 的 setup 里调用一次：
 *   const { paletteOpen } = useGlobalHotkeys({ router, onAction })
 *   返回的 paletteOpen 交给 <CommandPalette v-model:open="paletteOpen" ... />
 *
 * 键位表（工单验收）：
 *   Ctrl+K            命令面板
 *   Ctrl+N            上下文感知新建（对话页=新会话，ELN 页=新记录，其余默认新会话）
 *   Ctrl+1..5         分组直达（分组序号 = utils/navigation.ts groupIndexMap）
 *   Esc               全局关弹窗（含 PrimeVue Dialog —— 经 PrimeVue 的 Esc 处理兜底）
 *
 * 让位守卫（验收：快捷键在输入框聚焦时全部失效，打字不误触）：
 *   - 输入框聚焦（input/textarea/contenteditable）→ 全部放行给输入框
 *   - IME 组合中（isComposing / keyCode 229）→ 不拦截
 *   - 悬浮球模式（isFloating）→ 快捷键层整体停用
 */
import type { Router } from 'vue-router'
import { ref } from 'vue'
import { NAV_GROUPS } from '@/utils/navigation'

export interface HotkeyOptions {
  router: Router
  /** 动作回调（命令面板上抛）：new-eln / new-chat / doi-import */
  onAction?: (kind: 'new-eln' | 'new-chat' | 'doi-import') => void
  /** 悬浮球模式下停用（响应式布尔） */
  isFloating?: { value: boolean }
  /** 事件绑定目标（默认 window；测试可注入 mock） */
  target?: Pick<Window, 'addEventListener' | 'removeEventListener'>
}

/** 是否应放行给输入框（快捷键让位判定）——独立导出便于单测 */
export function shouldYieldToInput(event: KeyboardEvent): boolean {
  // IME 组合中：不拦
  if (event.isComposing || (event as KeyboardEvent & { keyCode?: number }).keyCode === 229)
    return true
  const el = event.target as HTMLElement | null
  if (!el)
    return false
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT')
    return true
  if (el.isContentEditable)
    return true
  return false
}

/** Ctrl+N 的上下文感知目标（纯函数，可单测） */
export function contextAwareNewAction(path: string): 'new-chat' | 'new-eln' {
  if (path.startsWith('/eln') || path.startsWith('/voice-eln'))
    return 'new-eln'
  // 对话页与其余场景默认新会话
  return 'new-chat'
}

export function useGlobalHotkeys(options: HotkeyOptions) {
  const paletteOpen = ref(false)
  const { router, onAction, isFloating, target } = options

  function firstPathOfGroup(index: number): string | null {
    const group = NAV_GROUPS[index - 1]
    return group?.items[0]?.to ?? null
  }

  function handler(event: KeyboardEvent) {
    if (isFloating?.value)
      return

    // 让位守卫：输入框/IME 聚焦时快捷键全部失效（Ctrl+K 面板自身的输入不受影响——
    // 面板 input 的 keydown 在组件内处理并 stopPropagation？不——事件仍冒泡到 window。
    // 所以这里排除"命令面板已打开"的情况：面板开着时 Esc 由面板自己关。）
    if (!paletteOpen.value && shouldYieldToInput(event))
      return

    const key = event.key.toLowerCase()

    // Esc：关闭命令面板（PrimeVue Dialog 的 Esc 由其自身处理，这里不重复）
    if (key === 'escape') {
      if (paletteOpen.value) {
        event.preventDefault()
        paletteOpen.value = false
      }
      return
    }

    if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey)
      return

    // Ctrl+K → 命令面板
    if (key === 'k') {
      event.preventDefault()
      paletteOpen.value = !paletteOpen.value
      return
    }

    // Ctrl+N → 上下文感知新建
    if (key === 'n') {
      event.preventDefault()
      onAction?.(contextAwareNewAction(router.currentRoute.value.path))
      return
    }

    // Ctrl+1..9 → 分组直达
    const digit = Number(key)
    if (Number.isInteger(digit) && digit >= 1 && digit <= 9) {
      const to = firstPathOfGroup(digit)
      if (to) {
        event.preventDefault()
        router.push(to)
      }
    }
  }

  const bindTarget = target ?? window
  bindTarget.addEventListener('keydown', handler as EventListener)

  // App.vue 长驻，不需要 unbind；但暴露以便测试/特殊场景清理
  function dispose() {
    bindTarget.removeEventListener('keydown', handler as EventListener)
  }

  return { paletteOpen, dispose }
}
